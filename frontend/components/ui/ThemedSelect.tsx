"use client";

import { useCallback, useEffect, useId, useRef, useState } from "react";

export type ThemedSelectOption<T extends string = string> = {
  value: T;
  label: string;
};

type Props<T extends string = string> = {
  options: ThemedSelectOption<T>[];
  value: T;
  onChange: (value: T) => void;
  placeholder?: string;
  disabled?: boolean;
  className?: string;
};

export function ThemedSelect<T extends string = string>({
  options,
  value,
  onChange,
  placeholder,
  disabled = false,
  className = "",
}: Props<T>) {
  const [open, setOpen] = useState(false);
  const [focusedIdx, setFocusedIdx] = useState(-1);
  const containerRef = useRef<HTMLDivElement>(null);
  const listRef = useRef<HTMLUListElement>(null);
  const triggerId = useId();
  const closingRef = useRef(false);

  const selectedOption = options.find((opt) => opt.value === value);
  const displayLabel = selectedOption?.label || placeholder || "";

  const close = useCallback(() => {
    closingRef.current = true;
    setOpen(false);
    setFocusedIdx(-1);
  }, []);

  useEffect(() => {
    if (!open) return;
    closingRef.current = false;
    const handler = (event: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(event.target as Node)) {
        close();
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [open, close]);

  useEffect(() => {
    if (!open || focusedIdx < 0 || !listRef.current) return;
    const items = listRef.current.querySelectorAll('[role="option"]');
    items[focusedIdx]?.scrollIntoView({ block: "nearest" });
  }, [open, focusedIdx]);

  function handleKeyDown(event: React.KeyboardEvent) {
    if (disabled) return;
    if (!open) {
      if (event.key === "ArrowDown" || event.key === "ArrowUp" || event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        setOpen(true);
        const currentIdx = options.findIndex((opt) => opt.value === value);
        setFocusedIdx(currentIdx >= 0 ? currentIdx : 0);
      }
      return;
    }

    switch (event.key) {
      case "ArrowDown":
        event.preventDefault();
        setFocusedIdx((prev) => (prev + 1) % options.length);
        break;
      case "ArrowUp":
        event.preventDefault();
        setFocusedIdx((prev) => (prev - 1 + options.length) % options.length);
        break;
      case "Enter":
      case " ":
        event.preventDefault();
        if (focusedIdx >= 0 && focusedIdx < options.length) {
          onChange(options[focusedIdx].value);
          close();
        }
        break;
      case "Escape":
        event.preventDefault();
        close();
        break;
      case "Tab":
        close();
        break;
    }
  }

  function selectOption(optionValue: T) {
    onChange(optionValue);
    close();
  }

  function handleTriggerClick() {
    if (disabled || closingRef.current) return;
    if (!open) {
      const currentIdx = options.findIndex((opt) => opt.value === value);
      setFocusedIdx(currentIdx >= 0 ? currentIdx : 0);
      setOpen(true);
    } else {
      close();
    }
  }

  return (
    <div
      className={`themed-select-root ${className}`.trim()}
      ref={containerRef}
      onKeyDown={handleKeyDown}
    >
      <button
        aria-controls={`${triggerId}-listbox`}
        aria-expanded={open}
        aria-haspopup="listbox"
        className="themed-select-trigger"
        disabled={disabled}
        id={triggerId}
        onClick={handleTriggerClick}
        type="button"
      >
        <span className={selectedOption ? "themed-select-trigger-value" : "themed-select-trigger-placeholder"}>
          {displayLabel}
        </span>
        <svg
          aria-hidden="true"
          className={`themed-select-chevron ${open ? "themed-select-chevron-open" : ""}`}
          fill="none"
          height="14"
          viewBox="0 0 14 14"
          width="14"
        >
          <path
            d="M3 5.25L7 9.25L11 5.25"
            stroke="#f3f7fb"
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth="1.6"
          />
        </svg>
      </button>
      {open ? (
        <ul
          aria-labelledby={triggerId}
          className="themed-select-dropdown"
          id={`${triggerId}-listbox`}
          ref={listRef}
          role="listbox"
        >
          {options.map((option, idx) => {
            const isSelected = option.value === value;
            const isFocused = idx === focusedIdx;
            return (
              <li
                aria-selected={isSelected}
                className={`themed-select-option${isSelected ? " themed-select-option-selected" : ""}${isFocused ? " themed-select-option-focused" : ""}`}
                key={option.value}
                onMouseDown={(event) => {
                  event.preventDefault();
                  event.stopPropagation();
                  selectOption(option.value);
                }}
                onMouseEnter={() => setFocusedIdx(idx)}
                role="option"
              >
                <span className="themed-select-option-label">{option.label}</span>
                {isSelected ? (
                  <svg
                    aria-hidden="true"
                    className="themed-select-option-check"
                    fill="none"
                    height="14"
                    viewBox="0 0 14 14"
                    width="14"
                  >
                    <path
                      d="M2.5 7L5.5 10L11.5 4"
                      stroke="#39d0ff"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth="1.8"
                    />
                  </svg>
                ) : null}
              </li>
            );
          })}
        </ul>
      ) : null}
    </div>
  );
}
