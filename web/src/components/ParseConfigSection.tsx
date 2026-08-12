import { forwardRef, useCallback, useEffect, useImperativeHandle, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { fetchPreviewMessages, type TestMessage } from "../lib/discordBridge";
import { formatApiError } from "../lib/apiError";
import {
  bootstrapParseRuleAi,
  copyParseRules,
  deleteParseRule,
  fetchParseRules,
  generateParseRule,
  nextParseRulePriority,
  saveParseRule,
  suggestParseRuleLabel,
  type ParseRule,
} from "../lib/parseRules";
import {
  buildExpectedOutput,
  DEFAULT_FLOW_SAMPLE,
  DEFAULT_PARSE_EXPECTED_FORM,
  formFromExpectedOutput,
  inferExpectedFormFromSample,
  resolveExpectedFormForGenerate,
  SPY_OPTION_FLOW_EXPECTED_FORM,
  SPY_OPTION_FLOW_SAMPLE,
  SPY_STOCK_EXPECTED_FORM,
  SPY_STOCK_SAMPLE,
} from "../lib/parseExpectedFields";
import ParseExpectedFieldsForm from "./ParseExpectedFieldsForm";
import UiSelect from "./UiSelect";
import type { ParseExpectedForm } from "../lib/parseExpectedFields";

type ParseableSource = {
  source_id: string;
  name: string;
  channel_ids?: string[];
  chat_ids?: string[];
  bridge_mode?: string;
  is_active?: boolean;
  kind?: "discord" | "webhook" | "telegram";
};

function isParseableSource(s: ParseableSource): boolean {
  const kind = s.kind || (s.source_id.startsWith("tg-") ? "telegram" : s.source_id.startsWith("wh-") ? "webhook" : "discord");
  if (kind === "telegram") return true;
  if (kind === "webhook") return true;
  return s.bridge_mode === "personal" && (s.channel_ids?.length ?? 0) > 0;
}

const PARSE_MODE = "example";

type Props = {
  sources: ParseableSource[];
  defaultSourceId?: string;
  fixedSourceId?: string;
  embedWizard?: boolean;
  onSaved?: () => void;
  onError?: (message: string) => void;
  onCanProceedChange?: (can: boolean) => void;
};

export type ParseConfigHandle = {
  save: () => Promise<boolean>;
  canProceed: () => boolean;
};

function ParseRuleModal({
  open,
  title,
  closeLabel,
  onClose,
  children,
  footer,
}: {
  open: boolean;
  title: string;
  closeLabel: string;
  onClose: () => void;
  children: React.ReactNode;
  footer: React.ReactNode;
}) {
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center p-0 sm:items-center sm:p-4">
      <button
        type="button"
        className="absolute inset-0 bg-slate-900/40"
        aria-label={closeLabel}
        onClick={onClose}
      />
      <div
        role="dialog"
        aria-modal="true"
        className="relative flex max-h-[92vh] w-full max-w-3xl flex-col overflow-hidden rounded-t-2xl border border-slate-200 bg-white shadow-xl sm:rounded-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between gap-3 border-b border-slate-200 px-5 py-4">
          <h3 className="text-base font-semibold text-slate-900">{title}</h3>
          <button type="button" className="text-sm text-slate-500 hover:text-slate-700" onClick={onClose}>
            {closeLabel}
          </button>
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto px-5 py-4">{children}</div>
        <div className="flex flex-wrap items-center justify-end gap-2 border-t border-slate-200 bg-slate-50/80 px-5 py-3">
          {footer}
        </div>
      </div>
    </div>
  );
}

function loadRuleIntoEditor(
  rule: ParseRule | null,
  setters: {
    setSample: (v: string) => void;
    setExpectedForm: (v: ParseExpectedForm) => void;
    setGeneratedConfig: (v: Record<string, unknown> | null) => void;
    setGeneratedSummary: (v: string) => void;
    setRuleLabel: (v: string) => void;
    setEditingPriority: (v: number) => void;
    setIsNewRule: (v: boolean) => void;
    setAuthorFilterEnabled: (v: boolean) => void;
    setAllowedAuthor: (v: string) => void;
  },
) {
  if (!rule) {
    setters.setIsNewRule(true);
    setters.setRuleLabel("example");
    setters.setSample(DEFAULT_FLOW_SAMPLE);
    setters.setExpectedForm(DEFAULT_PARSE_EXPECTED_FORM);
    setters.setGeneratedConfig(null);
    setters.setGeneratedSummary("");
    setters.setEditingPriority(10);
    setters.setAuthorFilterEnabled(false);
    setters.setAllowedAuthor("");
    return;
  }
  setters.setIsNewRule(false);
  setters.setRuleLabel(rule.label);
  setters.setEditingPriority(rule.priority);
  const cfg = rule.config || {};
  setters.setAuthorFilterEnabled(Boolean(cfg.author_filter));
  setters.setAllowedAuthor(typeof cfg.allowed_author === "string" ? cfg.allowed_author : "");
  setters.setGeneratedConfig(cfg);
  setters.setGeneratedSummary(typeof cfg.pattern === "string" ? String(cfg.pattern) : "");
  const ex = cfg.example as { sample?: string; expected_output?: Record<string, unknown> } | undefined;
  setters.setSample(ex?.sample || DEFAULT_FLOW_SAMPLE);
  setters.setExpectedForm(
    ex?.expected_output ? formFromExpectedOutput(ex.expected_output) : DEFAULT_PARSE_EXPECTED_FORM,
  );
}

const ParseConfigSection = forwardRef<ParseConfigHandle, Props>(function ParseConfigSection(
  { sources, defaultSourceId, fixedSourceId, embedWizard, onSaved, onError, onCanProceedChange },
  ref,
) {
  const { t } = useTranslation();
  const parseableSources = useMemo(() => sources.filter(isParseableSource), [sources]);

  const [sourceId, setSourceId] = useState("");
  const [savedRules, setSavedRules] = useState<ParseRule[]>([]);
  const [allRules, setAllRules] = useState<ParseRule[]>([]);
  const [copyFromId, setCopyFromId] = useState("");
  const [ruleModalOpen, setRuleModalOpen] = useState(false);
  const [isNewRule, setIsNewRule] = useState(true);
  const [ruleLabel, setRuleLabel] = useState("example");
  const [editingPriority, setEditingPriority] = useState(10);
  const [sample, setSample] = useState(DEFAULT_FLOW_SAMPLE);
  const [expectedForm, setExpectedForm] = useState<ParseExpectedForm>(DEFAULT_PARSE_EXPECTED_FORM);
  const [generatedConfig, setGeneratedConfig] = useState<Record<string, unknown> | null>(null);
  const [generatedSummary, setGeneratedSummary] = useState("");
  const [authorFilterEnabled, setAuthorFilterEnabled] = useState(false);
  const [allowedAuthor, setAllowedAuthor] = useState("");
  const [recentMessages, setRecentMessages] = useState<TestMessage[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [savedOk, setSavedOk] = useState(false);

  const selectedSource = parseableSources.find((s) => s.source_id === sourceId);

  const editorSetters = useMemo(
    () => ({
      setSample,
      setExpectedForm,
      setGeneratedConfig,
      setGeneratedSummary,
      setRuleLabel,
      setEditingPriority,
      setIsNewRule,
      setAuthorFilterEnabled,
      setAllowedAuthor,
    }),
    [],
  );

  const sourceOptions = useMemo(
    () =>
      parseableSources.map((s) => ({
        value: s.source_id,
        label: `${s.name}${s.is_active === false ? ` (${t("dashboard.discordSourceStopped")})` : ""}`,
      })),
    [parseableSources, t],
  );

  const loadRulesForSource = useCallback(async (id: string) => {
    const all = await fetchParseRules();
    setAllRules(all);
    const rules = all
      .filter((r) => r.source_id === id)
      .sort((a, b) => b.priority - a.priority);
    setSavedRules(rules);
    return rules;
  }, []);

  const copyFromOptions = useMemo(() => {
    const bySource = new Map<string, number>();
    for (const r of allRules) {
      if (r.source_id === sourceId) continue;
      bySource.set(r.source_id, (bySource.get(r.source_id) || 0) + 1);
    }
    return [...bySource.entries()].map(([id, count]) => {
      const src = sources.find((s) => s.source_id === id);
      return {
        value: id,
        label: `${src?.name || id} (${count})`,
      };
    });
  }, [allRules, sourceId, sources]);

  const handleCopyFromSource = async () => {
    if (!sourceId || !copyFromId) return;
    setBusy(true);
    setError("");
    setSavedOk(false);
    try {
      const n = await copyParseRules(copyFromId, sourceId);
      await loadRulesForSource(sourceId);
      setSavedOk(true);
      onSaved?.();
      onError?.("");
      if (n <= 0) setError(t("dashboard.parseCopyEmpty"));
    } catch (e) {
      const msg = formatApiError(e, t);
      setError(msg);
      onError?.(msg);
    } finally {
      setBusy(false);
    }
  };

  const resetEditorForNewRule = useCallback((rules: ParseRule[]) => {
    setIsNewRule(true);
    setRuleLabel(suggestParseRuleLabel(PARSE_MODE, rules));
    setEditingPriority(nextParseRulePriority(rules));
    setSample(DEFAULT_FLOW_SAMPLE);
    setExpectedForm(DEFAULT_PARSE_EXPECTED_FORM);
      setGeneratedConfig(null);
      setGeneratedSummary("");
    setAuthorFilterEnabled(false);
    setAllowedAuthor("");
    setSavedOk(false);
    setError("");
  }, []);

  const openNewRuleModal = useCallback(() => {
    resetEditorForNewRule(savedRules);
    setRuleModalOpen(true);
  }, [resetEditorForNewRule, savedRules]);

  const openEditRuleModal = useCallback(
    (rule: ParseRule) => {
      loadRuleIntoEditor(rule, editorSetters);
      setSavedOk(false);
      setError("");
      setRuleModalOpen(true);
    },
    [editorSetters],
  );

  const closeRuleModal = useCallback(() => {
    setRuleModalOpen(false);
    setError("");
  }, []);

  useEffect(() => {
    if (fixedSourceId) {
      setSourceId(fixedSourceId);
      return;
    }
    if (parseableSources.length === 0) {
      setSourceId("");
      return;
    }
    const preferred =
      (defaultSourceId && parseableSources.some((s) => s.source_id === defaultSourceId)
        ? defaultSourceId
        : null) || parseableSources[0]?.source_id;
    setSourceId((prev) =>
      prev && parseableSources.some((s) => s.source_id === prev) ? prev : preferred || "",
    );
  }, [parseableSources, defaultSourceId, fixedSourceId]);

  useEffect(() => {
    if (!sourceId) return;
    setSavedOk(false);
    setError("");
    setRuleModalOpen(false);
    void loadRulesForSource(sourceId);
    void fetchPreviewMessages(sourceId)
      .then((msgs) => setRecentMessages(msgs.slice(0, 8)))
      .catch(() => setRecentMessages([]));
  }, [sourceId, loadRulesForSource]);

  const canSaveDraft = useCallback(() => {
    if (!sourceId || !ruleLabel.trim()) return false;
    if (authorFilterEnabled && !allowedAuthor.trim()) return false;
    if (!generatedConfig) return false;
    return true;
  }, [sourceId, ruleLabel, authorFilterEnabled, allowedAuthor, generatedConfig]);

  const canProceed = useCallback(
    () => savedRules.length > 0 || canSaveDraft(),
    [savedRules.length, canSaveDraft],
  );

  const handleSave = useCallback(
    async (closeOnSuccess = false): Promise<boolean> => {
      if (!sourceId) return false;
      if (canSaveDraft()) {
        if (authorFilterEnabled && !allowedAuthor.trim()) {
          const msg = t("dashboard.parseAuthorRequired");
          setError(msg);
          onError?.(msg);
          return false;
        }
        setBusy(true);
        setError("");
        onError?.("");
        setSavedOk(false);
        try {
          if (!generatedConfig) {
            const msg = t("dashboard.parseGenerateFirst");
            setError(msg);
            onError?.(msg);
            return false;
          }
          const config: Record<string, unknown> = { ...generatedConfig };
          if (authorFilterEnabled && allowedAuthor.trim()) {
            config.author_filter = true;
            config.allowed_author = allowedAuthor.trim();
          }
          await saveParseRule({
            source_id: sourceId,
            parse_mode: PARSE_MODE,
            priority: isNewRule ? nextParseRulePriority(savedRules) : editingPriority,
            label: ruleLabel.trim(),
            config,
          });
          const rules = await loadRulesForSource(sourceId);
          setSavedOk(true);
          setIsNewRule(false);
          onSaved?.();
          if (closeOnSuccess) setRuleModalOpen(false);
          return rules.length > 0;
        } catch (e) {
          const msg = formatApiError(e, t);
          setError(msg);
          onError?.(msg);
          return false;
        } finally {
          setBusy(false);
        }
      }
      if (savedRules.length > 0) {
        onSaved?.();
        return true;
      }
      return false;
    },
    [
      sourceId,
      canSaveDraft,
      generatedConfig,
      isNewRule,
      savedRules,
      editingPriority,
      ruleLabel,
      loadRulesForSource,
      onSaved,
      onError,
      t,
      authorFilterEnabled,
      allowedAuthor,
    ],
  );

  useImperativeHandle(ref, () => ({ save: () => handleSave(false), canProceed }), [handleSave, canProceed]);

  useEffect(() => {
    onCanProceedChange?.(canProceed());
  }, [canProceed, onCanProceedChange]);

  const runGenerate = async () => {
    if (!sample.trim()) {
      setError(t("dashboard.parseSampleRequired"));
      return;
    }
    const resolvedForm = resolveExpectedFormForGenerate(sample.trim(), expectedForm);
    if (resolvedForm !== expectedForm) setExpectedForm(resolvedForm);
    if (!resolvedForm.underlying.trim()) {
      setError(t("dashboard.parseUnderlyingRequired"));
      return;
    }
    setBusy(true);
    setError("");
    setSavedOk(false);
    try {
      const expected = buildExpectedOutput(resolvedForm);
      const result = await generateParseRule({ sample: sample.trim(), expected_output: expected });
      setGeneratedConfig(result.config);
      setGeneratedSummary(result.summary);
    } catch (e) {
      setError(formatApiError(e, t));
      setGeneratedConfig(null);
      setGeneratedSummary("");
    } finally {
      setBusy(false);
    }
  };

  const runAiBootstrap = async () => {
    if (!sample.trim()) {
      setError(t("dashboard.parseSampleRequired"));
      return;
    }
    setBusy(true);
    setError("");
    setSavedOk(false);
    try {
      const result = await bootstrapParseRuleAi({ sample: sample.trim() });
      if (result.expected_output) {
        setExpectedForm(formFromExpectedOutput(result.expected_output));
      }
      setGeneratedConfig(result.config);
      setGeneratedSummary(result.summary);
    } catch (e) {
      setError(formatApiError(e, t));
      setGeneratedConfig(null);
      setGeneratedSummary("");
    } finally {
      setBusy(false);
    }
  };

  const handleDeleteRule = async (label: string) => {
    if (!sourceId) return;
    setBusy(true);
    setError("");
    try {
      await deleteParseRule(sourceId, label);
      await loadRulesForSource(sourceId);
      onSaved?.();
    } catch (e) {
      setError(formatApiError(e, t));
    } finally {
      setBusy(false);
    }
  };

  const modalHint = t("dashboard.parseStep2ExampleB");

  const modalTitle = isNewRule
    ? t("dashboard.parseModalTitleNew")
    : t("dashboard.parseModalTitleEdit", { label: ruleLabel });

  if (!fixedSourceId && parseableSources.length === 0) {
    return (
      <p className="rounded-lg border border-dashed border-slate-200 bg-slate-50 px-4 py-6 text-sm text-slate-500">
        {t("dashboard.parseStepNeedSource")}
      </p>
    );
  }

  const isTelegramSource =
    sourceId.startsWith("tg-") || selectedSource?.kind === "telegram";

  return (
    <div className="space-y-5">
      {embedWizard ? (
        <div className="space-y-2">
          <p className="text-sm text-slate-600">{t("dashboard.parseStepHint")}</p>
          <p className="rounded-lg border border-brand-100 bg-brand-50/60 px-3 py-2 text-xs text-brand-800">
            {t("execPipeline.saveOnNextParse")}
          </p>
        </div>
      ) : null}

      <div className="space-y-4 rounded-xl border border-brand-100 bg-brand-50/40 p-4 lg:p-5">
        {!fixedSourceId ? (
          <div className="space-y-2 border-b border-brand-100 pb-4">
            <p className="text-sm font-medium text-slate-800">{t("dashboard.parseStep1Title")}</p>
            <p className="text-xs text-slate-500">{t("dashboard.parseStep1a")}</p>
            <UiSelect
                  value={sourceId}
              onChange={setSourceId}
              options={sourceOptions}
              placeholder={t("execPipeline.pickSource")}
            />
                {selectedSource ? (
                  <p className="text-xs text-slate-500">
                    {t("dashboard.parseSourceId")}:{" "}
                    <span className="font-mono text-slate-600">{selectedSource.source_id}</span>
                  </p>
                ) : null}
              </div>
        ) : null}

        {isTelegramSource && copyFromOptions.length > 0 ? (
          <div className="space-y-2 rounded-lg border border-slate-200 bg-white p-3">
            <p className="text-sm font-medium text-slate-800">{t("dashboard.parseCopyTitle")}</p>
            <p className="text-xs text-slate-500">{t("dashboard.parseCopyHint")}</p>
            <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
              <div className="min-w-0 flex-1">
                <UiSelect
                  value={copyFromId}
                  onChange={setCopyFromId}
                  options={copyFromOptions}
                  placeholder={t("dashboard.parseCopyPick")}
                />
              </div>
              <button
                type="button"
                className="btn-secondary shrink-0 text-sm"
                disabled={busy || !copyFromId}
                onClick={() => void handleCopyFromSource()}
              >
                {t("dashboard.parseCopyAction")}
              </button>
            </div>
          </div>
        ) : null}

        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <p className="text-sm font-medium text-slate-800">
              {savedRules.length > 0
                ? t("dashboard.parseSavedRulesTitle", { count: savedRules.length })
                : t("dashboard.parseNoRulesYet")}
            </p>
            <p className="mt-1 text-xs text-slate-500">{t("dashboard.parseSavedRulesHint")}</p>
          </div>
          <button type="button" className="btn-primary text-sm" disabled={busy} onClick={openNewRuleModal}>
            + {t("dashboard.parseAddRule")}
          </button>
        </div>

        {savedRules.length > 0 ? (
          <ul className="flex flex-wrap gap-2">
            {savedRules.map((rule) => (
              <li key={rule.label}>
                <div className="flex items-center gap-1 rounded-full border border-slate-200 bg-white px-2 py-1 text-xs text-slate-600">
                  <button
                    type="button"
                    className="font-medium hover:text-brand-700 hover:underline"
                    onClick={() => openEditRuleModal(rule)}
                  >
                    {rule.label}
                    {rule.config?.author_filter && rule.config?.allowed_author ? (
                      <span className="ml-1 text-brand-600">
                        · {t("dashboard.parseAuthorBadge", { author: String(rule.config.allowed_author) })}
                      </span>
                    ) : null}
                  </button>
                  <span className="text-slate-400">P{rule.priority}</span>
                  <button
                    type="button"
                    className="ml-0.5 text-slate-400 hover:text-loss"
                    title={t("dashboard.parseDeleteRule")}
                    disabled={busy}
                    onClick={() => void handleDeleteRule(rule.label)}
                  >
                    ×
                  </button>
                </div>
              </li>
            ))}
          </ul>
        ) : (
          <button
            type="button"
            className="w-full rounded-lg border border-dashed border-slate-200 bg-white px-4 py-8 text-center text-sm text-slate-500 transition-colors hover:border-brand-200 hover:bg-brand-50/40"
            disabled={busy}
            onClick={openNewRuleModal}
          >
            {t("dashboard.parseNoRulesYet")}
          </button>
        )}

        {savedOk && !ruleModalOpen ? (
          <p className="text-xs text-profit">{t("dashboard.parseSaved")}</p>
        ) : null}
        {error && !ruleModalOpen ? <p className="text-xs text-loss">{error}</p> : null}
      </div>

      <ParseRuleModal
        open={ruleModalOpen}
        title={modalTitle}
        closeLabel={t("dashboard.parseModalClose")}
        onClose={closeRuleModal}
        footer={
          <>
            <button
              type="button"
              className="btn-secondary text-sm"
              disabled={busy || !sample.trim()}
              onClick={() => void runGenerate()}
            >
              {t("dashboard.parseGenerateRuleManual")}
            </button>
            <button
              type="button"
              className="btn-primary text-sm"
              disabled={busy || !sample.trim()}
              onClick={() => void runAiBootstrap()}
            >
              {busy ? t("common.loading") : t("dashboard.parseAiBootstrap")}
            </button>
            <button
              type="button"
              className="btn-primary text-sm"
              disabled={busy || !canSaveDraft()}
              onClick={() => void handleSave(true)}
            >
              {t("dashboard.parseSaveRule")}
            </button>
          </>
        }
      >
        <p className="text-xs text-slate-500">{t("dashboard.parseMultiRuleHint")}</p>
        <p className="mt-1 text-xs text-slate-500">{modalHint}</p>

        {error ? (
          <div className="mt-3 rounded-lg border border-loss/20 bg-loss-soft px-3 py-2 text-sm text-loss">
            {error}
          </div>
        ) : null}

        <div className="mt-4 space-y-3">
          <div className="space-y-1.5">
            <label className="text-xs font-medium text-slate-500">{t("dashboard.parseRuleLabel")}</label>
            <input
              className="input w-full text-sm"
              value={ruleLabel}
              disabled={!isNewRule || busy}
              placeholder={t("dashboard.parseRuleLabelPlaceholder")}
              onChange={(e) => setRuleLabel(e.target.value)}
            />
          </div>
          <div className="rounded-lg border border-slate-200 bg-slate-50/80 p-3 space-y-2">
            <label className="flex cursor-pointer items-start gap-2">
              <input
                type="checkbox"
                className="mt-0.5"
                checked={authorFilterEnabled}
                disabled={busy}
                onChange={(e) => {
                  setAuthorFilterEnabled(e.target.checked);
                  if (!e.target.checked) setAllowedAuthor("");
                  setError("");
                }}
              />
              <span className="text-sm text-slate-700">{t("dashboard.parseAuthorFilter")}</span>
            </label>
            {authorFilterEnabled ? (
              <div className="space-y-1.5 pl-6">
                <label className="text-xs font-medium text-slate-500">{t("dashboard.parseAllowedAuthor")}</label>
                <input
                  className="input w-full text-sm"
                  value={allowedAuthor}
                  disabled={busy}
                  placeholder={t("dashboard.parseAllowedAuthorPlaceholder")}
                  onChange={(e) => setAllowedAuthor(e.target.value)}
                />
                <p className="text-xs text-slate-500">{t("dashboard.parseAuthorFilterHint")}</p>
              </div>
            ) : null}
          </div>

          <div className="grid gap-3 lg:grid-cols-2">
                  <div className="space-y-1.5">
              <div className="flex flex-wrap items-center justify-between gap-2">
                    <p className="text-xs font-medium text-slate-500">{t("dashboard.parseColInput")}</p>
                <div className="flex flex-wrap gap-2">
                  <button
                    type="button"
                    className="text-[11px] text-brand-600 hover:underline"
                    disabled={busy}
                    onClick={() => {
                      setSample(DEFAULT_FLOW_SAMPLE);
                      setExpectedForm(DEFAULT_PARSE_EXPECTED_FORM);
                      setGeneratedConfig(null);
                      setGeneratedSummary("");
                    }}
                  >
                    {t("dashboard.parseLoadDefaultExample")}
                  </button>
                  <button
                    type="button"
                    className="text-[11px] text-brand-600 hover:underline"
                    disabled={busy}
                    onClick={() => {
                      setSample(SPY_STOCK_SAMPLE);
                      setExpectedForm(SPY_STOCK_EXPECTED_FORM);
                      setGeneratedConfig(null);
                      setGeneratedSummary("");
                    }}
                  >
                    {t("dashboard.parseLoadSpyStockExample")}
                  </button>
                  <button
                    type="button"
                    className="text-[11px] text-brand-600 hover:underline"
                    disabled={busy}
                    onClick={() => {
                      setSample(SPY_OPTION_FLOW_SAMPLE);
                      setExpectedForm(SPY_OPTION_FLOW_EXPECTED_FORM);
                      setGeneratedConfig(null);
                      setGeneratedSummary("");
                    }}
                  >
                    {t("dashboard.parseLoadSpyOptionExample")}
                  </button>
                </div>
              </div>
                    <textarea
                      className="textarea w-full font-mono text-xs"
                rows={8}
                      placeholder={t("dashboard.parseOptionSamplePlaceholder")}
                      value={sample}
                      onChange={(e) => {
                        setSample(e.target.value);
                        setGeneratedConfig(null);
                        setGeneratedSummary("");
                      }}
                    />
                  </div>
                  <div className="space-y-1.5">
                    <p className="text-xs font-medium text-slate-500">{t("dashboard.parseColOutput")}</p>
              <ParseExpectedFieldsForm
                value={expectedForm}
                disabled={busy}
                onChange={(next) => {
                  setExpectedForm(next);
                  setGeneratedConfig(null);
                  setGeneratedSummary("");
                }}
                    />
                  </div>
            {generatedSummary ? (
              <div className="space-y-1.5 lg:col-span-2">
                <p className="text-xs font-medium text-slate-500">{t("dashboard.parseColRule")}</p>
                <pre className="code-block max-h-32 overflow-auto whitespace-pre-wrap text-xs text-slate-700">
                  {generatedSummary}
                </pre>
                </div>
                  ) : null}
          </div>

              {recentMessages.length > 0 ? (
                <div className="space-y-1.5">
                  <p className="text-xs font-medium text-slate-500">{t("dashboard.parsePickFromMonitor")}</p>
                  <ul className="flex flex-wrap gap-1.5">
                    {recentMessages.map((m) => (
                      <li key={m.message_id}>
                        <button
                          type="button"
                          className="max-w-full truncate rounded-full border border-slate-200 bg-white px-2.5 py-1 text-left text-xs text-slate-600 hover:border-brand-300 hover:bg-brand-50"
                          title={`${m.author}: ${m.content}`}
                          onClick={() => {
                            setSample(m.content);
                            const inferred = inferExpectedFormFromSample(m.content);
                            if (inferred) {
                              setExpectedForm((prev) => ({ ...prev, ...inferred }));
                            }
                            setGeneratedConfig(null);
                            setGeneratedSummary("");
                          }}
                        >
                          {m.author}: {m.content.slice(0, 28)}
                          {m.content.length > 28 ? "…" : ""}
                        </button>
                      </li>
                    ))}
                  </ul>
                </div>
              ) : null}

              {savedOk ? <p className="text-xs text-profit">{t("dashboard.parseSaved")}</p> : null}
            </div>
      </ParseRuleModal>
      </div>
  );
});

export default ParseConfigSection;
