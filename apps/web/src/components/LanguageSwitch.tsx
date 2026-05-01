import type { Language } from "../i18n/messages";

type Props = {
  language: Language;
  onChange: (language: Language) => void;
};

export function LanguageSwitch({ language, onChange }: Props) {
  return (
    <div className="grid grid-cols-2 gap-1 rounded-2xl border border-console-line bg-console-surface p-1" aria-label="Language">
      <button
        type="button"
        className={buttonClass(language === "zh")}
        onClick={() => onChange("zh")}
      >
        中文
      </button>
      <button
        type="button"
        className={buttonClass(language === "en")}
        onClick={() => onChange("en")}
      >
        EN
      </button>
    </div>
  );
}

function buttonClass(active: boolean) {
  return [
    "min-h-10 rounded-xl px-3 text-sm transition-colors",
    active ? "bg-console-ink text-console-surface" : "text-console-muted hover:bg-console-canvas"
  ].join(" ");
}
