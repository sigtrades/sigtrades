import { useEffect, useId, useRef, useState } from "react";
import { createPortal } from "react-dom";

export type UiSelectOption = {
  value: string;
  label: string;
  disabled?: boolean;
  /** 右侧小标签，如「模拟」「线上」 */
  tag?: string;
  tagTone?: "paper" | "live" | "neutral";
};

function OptionTag({ tag, tagTone }: { tag: string; tagTone?: UiSelectOption["tagTone"] }) {
  const tone =
    tagTone === "live"
      ? "bg-emerald-50 text-emerald-700 ring-emerald-200"
      : tagTone === "paper"
        ? "bg-amber-50 text-amber-800 ring-amber-200"
        : "bg-slate-100 text-slate-600 ring-slate-200";
  return (
    <span
      className={`inline-flex shrink-0 items-center rounded-full px-1.5 py-0.5 text-[10px] font-semibold ring-1 ${tone}`}
    >
      {tag}
    </span>
  );
}

type Props = {
  value: string;
  onChange: (value: string) => void;
  options: UiSelectOption[];
  placeholder?: string;
  disabled?: boolean;
  className?: string;
  "aria-label"?: string;
};

export default function UiSelect({
  value,
  onChange,
  options,
  placeholder = "—",
  disabled = false,
  className = "",
  "aria-label": ariaLabel,
}: Props) {
  const [open, setOpen] = useState(false);
  const [menuStyle, setMenuStyle] = useState<{
    left: number;
    top?: number;
    bottom?: number;
    width: number;
    maxHeight: number;
  } | null>(null);
  const rootRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const menuRef = useRef<HTMLUListElement>(null);
  const listId = useId();
  const selected = options.find((o) => o.value === value);

  useEffect(() => {
    if (!open) return;
    const onDoc = (e: MouseEvent) => {
      const target = e.target as Node;
      if (
        !rootRef.current?.contains(target)
        && !menuRef.current?.contains(target)
      ) {
        setOpen(false);
      }
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", onDoc);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDoc);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  useEffect(() => {
    if (!open) {
      setMenuStyle(null);
      return;
    }
    const updatePosition = () => {
      const rect = triggerRef.current?.getBoundingClientRect();
      if (!rect) return;
      const viewportPadding = 8;
      const gap = 4;
      const availableBelow = window.innerHeight - rect.bottom - viewportPadding;
      const availableAbove = rect.top - viewportPadding;
      const openAbove = availableBelow < 160 && availableAbove > availableBelow;
      const maxHeight = Math.max(
        96,
        Math.min(240, (openAbove ? availableAbove : availableBelow) - gap),
      );
      const width = Math.min(rect.width, window.innerWidth - viewportPadding * 2);
      const left = Math.min(
        Math.max(viewportPadding, rect.left),
        window.innerWidth - width - viewportPadding,
      );
      setMenuStyle({
        left,
        width,
        maxHeight,
        ...(openAbove
          ? { bottom: window.innerHeight - rect.top + gap }
          : { top: rect.bottom + gap }),
      });
    };
    updatePosition();
    window.addEventListener("resize", updatePosition);
    window.addEventListener("scroll", updatePosition, true);
    return () => {
      window.removeEventListener("resize", updatePosition);
      window.removeEventListener("scroll", updatePosition, true);
    };
  }, [open]);

  return (
    <div ref={rootRef} className={`relative ${className}`}>
      <button
        ref={triggerRef}
        type="button"
        disabled={disabled}
        aria-label={ariaLabel}
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-controls={listId}
        onClick={() => !disabled && setOpen((v) => !v)}
        className={`flex w-full items-center justify-between gap-2 rounded-lg border border-slate-300 bg-white px-3 py-2 text-left text-sm text-slate-900 transition-colors hover:border-slate-400 focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-100 disabled:cursor-not-allowed disabled:opacity-50 ${
          open ? "border-brand-500 ring-2 ring-brand-100" : ""
        }`}
      >
        <span className="flex min-w-0 flex-1 items-center gap-2">
          <span className={selected ? "truncate" : "truncate text-slate-400"}>
            {selected?.label ?? placeholder}
          </span>
          {selected?.tag ? <OptionTag tag={selected.tag} tagTone={selected.tagTone} /> : null}
        </span>
        <svg
          viewBox="0 0 20 20"
          fill="currentColor"
          className={`h-4 w-4 shrink-0 text-slate-400 transition-transform ${open ? "rotate-180" : ""}`}
          aria-hidden
        >
          <path
            fillRule="evenodd"
            d="M5.23 7.21a.75.75 0 011.06.02L10 10.94l3.71-3.71a.75.75 0 111.06 1.06l-4.24 4.25a.75.75 0 01-1.06 0L5.21 8.29a.75.75 0 01.02-1.06z"
            clipRule="evenodd"
          />
        </svg>
      </button>
      {open && menuStyle ? createPortal(
        <ul
          ref={menuRef}
          id={listId}
          role="listbox"
          className="fixed z-[100] overflow-auto rounded-lg border border-slate-200 bg-white py-1 shadow-xl ring-1 ring-slate-100"
          style={menuStyle}
        >
          {options.map((opt) => {
            const active = opt.value === value;
            return (
              <li key={opt.value} role="option" aria-selected={active}>
                <button
                  type="button"
                  disabled={opt.disabled}
                  className={`flex w-full items-center justify-between gap-2 px-3 py-2 text-left text-sm transition-colors ${
                    active
                      ? "bg-brand-50 font-medium text-brand-800"
                      : "text-slate-700 hover:bg-slate-50"
                  } ${opt.disabled ? "cursor-not-allowed opacity-40" : ""}`}
                  onClick={() => {
                    if (opt.disabled) return;
                    onChange(opt.value);
                    setOpen(false);
                  }}
                >
                  <span className="min-w-0 truncate">{opt.label}</span>
                  {opt.tag ? <OptionTag tag={opt.tag} tagTone={opt.tagTone} /> : null}
                </button>
              </li>
            );
          })}
        </ul>
      , document.body) : null}
    </div>
  );
}
