from __future__ import annotations

from statistics import mean
from typing import Any


def _to_number(value: Any) -> float | None:
    if value in (None, ""):
        return None
    if isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _format_number(value: float) -> str:
    if value.is_integer():
        return str(int(value))
    return f"{value:.2f}"


def _is_dimension_column(rows: list[dict[str, Any]], column: str) -> bool:
    return any(_to_number(row.get(column)) is None and row.get(column) not in (None, "") for row in rows)


def _pick_numeric_columns(columns: list[str], rows: list[dict[str, Any]]) -> list[str]:
    numeric_columns: list[str] = []
    for column in columns:
        values = [_to_number(row.get(column)) for row in rows]
        if any(value is not None for value in values):
            numeric_columns.append(column)
    return numeric_columns


def _pick_dimension_column(columns: list[str], rows: list[dict[str, Any]]) -> str | None:
    preferred_keywords = ("name", "customer", "owner", "负责人", "客户", "月份", "日期", "类型")
    candidates = [column for column in columns if _is_dimension_column(rows, column)]
    for keyword in preferred_keywords:
        for column in candidates:
            if keyword.lower() in column.lower():
                return column
    return candidates[0] if candidates else None


def _build_metric_explanations(numeric_columns: list[str], rows: list[dict[str, Any]]) -> list[str]:
    explanations: list[str] = []
    for column in numeric_columns[:4]:
        values = [_to_number(row.get(column)) for row in rows]
        clean_values = [value for value in values if value is not None]
        if not clean_values:
            continue
        explanations.append(
            f"{column}：合计 {_format_number(sum(clean_values))}，"
            f"均值 {_format_number(mean(clean_values))}，"
            f"最大 {_format_number(max(clean_values))}，最小 {_format_number(min(clean_values))}"
        )
    return explanations


def _build_trend_insights(question: str, numeric_columns: list[str], rows: list[dict[str, Any]]) -> list[str]:
    if len(rows) < 2 or not numeric_columns:
        return []

    insights: list[str] = []
    for column in numeric_columns[:2]:
        first = _to_number(rows[0].get(column))
        last = _to_number(rows[-1].get(column))
        if first is None or last is None:
            continue
        delta = last - first
        if delta == 0:
            direction = "基本持平"
            ratio_text = "变化率 0%"
        else:
            direction = "上升" if delta > 0 else "下降"
            ratio = abs(delta) / abs(first) * 100 if first else 0
            ratio_text = f"变化率 {ratio:.1f}%" if first else "首期为 0，暂不计算变化率"
        insights.append(
            f"{column} 从 {_format_number(first)} 到 {_format_number(last)}，"
            f"{direction} {_format_number(abs(delta))}，{ratio_text}"
        )
    return insights


def _build_anomaly_insights(numeric_columns: list[str], rows: list[dict[str, Any]], dimension_column: str | None) -> list[str]:
    insights: list[str] = []
    for column in numeric_columns[:3]:
        pairs: list[tuple[float, dict[str, Any]]] = []
        for row in rows:
            value = _to_number(row.get(column))
            if value is not None:
                pairs.append((value, row))
        if len(pairs) < 3:
            continue

        values = [item[0] for item in pairs]
        avg_value = mean(values)
        if avg_value == 0:
            continue
        max_value, max_row = max(pairs, key=lambda item: item[0])
        min_value, min_row = min(pairs, key=lambda item: item[0])
        if max_value >= avg_value * 1.5:
            label = max_row.get(dimension_column) if dimension_column else "最高值"
            insights.append(f"{column} 在 {label} 明显偏高，达到均值的 {max_value / avg_value:.1f} 倍")
        if min_value <= avg_value * 0.5:
            label = min_row.get(dimension_column) if dimension_column else "最低值"
            insights.append(f"{column} 在 {label} 明显偏低，仅为均值的 {min_value / avg_value:.1f} 倍")
    return insights[:4]


def _build_topn_attribution(numeric_columns: list[str], rows: list[dict[str, Any]], dimension_column: str | None) -> list[str]:
    if not numeric_columns or not dimension_column:
        return []

    column = numeric_columns[0]
    pairs: list[tuple[float, dict[str, Any]]] = []
    for row in rows:
        value = _to_number(row.get(column))
        if value is not None:
            pairs.append((value, row))
    if not pairs:
        return []

    total = sum(value for value, _ in pairs)
    top_items = sorted(pairs, key=lambda item: item[0], reverse=True)[:3]
    insights: list[str] = []
    for value, row in top_items:
        label = row.get(dimension_column) or "未命名维度"
        share_text = f"，占比 {value / total * 100:.1f}%" if total else ""
        insights.append(f"{label} 对 {column} 贡献 {_format_number(value)}{share_text}")
    return insights


def analyze_query_result(question: str, query_output: dict[str, Any]) -> dict[str, Any]:
    """基于 data.query_sql 的结构化结果生成经营解释，V1 先保持确定性和可回归。"""
    query_result = query_output.get("result") or {}
    columns = list(query_result.get("columns") or [])
    rows = list(query_result.get("rows") or [])
    numeric_columns = _pick_numeric_columns(columns, rows)
    dimension_column = _pick_dimension_column(columns, rows)

    metric_explanations = _build_metric_explanations(numeric_columns, rows)
    trend_insights = _build_trend_insights(question, numeric_columns, rows)
    anomaly_insights = _build_anomaly_insights(numeric_columns, rows, dimension_column)
    topn_attribution = _build_topn_attribution(numeric_columns, rows, dimension_column)

    if query_output.get("error"):
        summary = "数据查询未成功，暂时无法形成经营分析。"
    elif not rows:
        summary = "查询没有返回数据，暂未发现可解释的经营变化。"
    elif any((keyword in question) for keyword in ("为什么", "原因", "下降", "变差")):
        summary = "已根据查询结果提取可能影响指标变化的维度和异常点。"
    else:
        summary = "已根据查询结果生成趋势、异常、指标和 TopN 归因摘要。"

    return {
        "protocol": "data.analyze_business.v1",
        "question": question,
        "summary": summary,
        "row_count": int(query_result.get("row_count") or len(rows)),
        "metric_explanations": metric_explanations,
        "trend_insights": trend_insights,
        "anomaly_insights": anomaly_insights,
        "topn_attribution": topn_attribution,
        "data_shape": {
            "columns": columns,
            "numeric_columns": numeric_columns,
            "dimension_column": dimension_column,
        },
    }
