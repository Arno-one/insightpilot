from dataclasses import dataclass

from app.core.config import settings


@dataclass(frozen=True)
class DocumentChunk:
    doc_id: str
    section_id: str
    title: str
    text: str
    chunk_index: int


def split_markdown(doc_id: str, title: str, text: str) -> list[DocumentChunk]:
    """按架构文档要求切片：chunk_size=500，overlap=50，优先按段落和句子切。"""
    try:
        from langchain_text_splitters import RecursiveCharacterTextSplitter

        splitter = RecursiveCharacterTextSplitter(
            chunk_size=settings.rag_chunk_size,
            chunk_overlap=settings.rag_chunk_overlap,
            separators=["\n\n", "\n", "。", "，", " "],
        )
        parts = splitter.split_text(text)
    except Exception:
        # 中文注释：依赖异常时使用简单滑窗降级，保证入库流程不断。
        size = settings.rag_chunk_size
        overlap = settings.rag_chunk_overlap
        step = max(size - overlap, 1)
        parts = [text[i : i + size] for i in range(0, len(text), step)]

    chunks: list[DocumentChunk] = []
    current_section = "ROOT"
    for index, part in enumerate(parts):
        for line in part.splitlines():
            if line.startswith("## "):
                current_section = line.strip("# ").strip().split(" ", 1)[0]
                break
        chunks.append(
            DocumentChunk(
                doc_id=doc_id,
                section_id=current_section or "ROOT",
                title=title,
                text=part.strip(),
                chunk_index=index,
            )
        )
    return [chunk for chunk in chunks if chunk.text]
