// LOSSQ_CORRECT_PROJECT_REDEPLOY_20260611210133
"use client";

// LOSSQ_MANUAL_EXPOSURE_INPUTS_FRONTEND_REDEPLOY_V2

import { useRouter } from "next/navigation";
import { useEffect, useState, useRef, type ReactNode } from "react";
import {
  BarChart,
  Bar,
  LineChart,
  Line,
  PieChart,
  Pie,
  Cell,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from "recharts";

const API =
  process.env.NEXT_PUBLIC_API_URL || "https://lossq-production.up.railway.app";

const SESSION_TIMEOUT_MS = 1000 * 60 * 60 * 24;
const PROFILE_CACHE_KEY = "lossq_account_profiles";
const SELECTED_POLICY_CACHE_KEY = "lossq_selected_policy_number";
const SELECTED_CLAIM_CACHE_KEY = "lossq_selected_claim";
const CURRENT_UPLOAD_CACHE_KEY = "lossq_current_upload_claims";

// LOSSQ_FRONTEND_PLAN_FUNCTION_LIMITS_V1
const LOSSQ_PLAN_FUNCTION_LIMITS: Record<string, string[]> = {
  // LOSSQ_FRONTEND_BETA_ACCESS_PLAN_V1
  beta: [
    "overview",
    "account_profiles",
    "loss_run_upload",
    "claims_analysis",
    "renewal_score",
    "renewal_memo",
    "reports",
    "pdf_exports",
    "copilot",
    "carrier_packet",
    "submission_builder",
    "carrier_email_draft",
    "charts",
  ],

  free: [
    "overview",
    "account_profiles",
    "loss_run_upload",
    "claims_dashboard",
    "exposure_inputs",
  ],
  starter: [
    "overview",
    "account_profiles",
    "loss_run_upload",
    "claims_dashboard",
    "exposure_inputs",
    "ai_summary",
    "renewal_memo",
    "pdf_exports",
  ],
  professional: [
    "overview",
    "account_profiles",
    "loss_run_upload",
    "claims_dashboard",
    "exposure_inputs",
    "ai_summary",
    "renewal_memo",
    "pdf_exports",
    "renewal_risk",
    "underwriter_decision",
    "carrier_appetite",
    "carrier_match",
    "submission_readiness",
    "premium_forecast",
    "submission_builder",
    "carrier_packet",
    "carrier_email_draft",
    "advanced_analytics",
    "charts",


  ],
  agency: [
    "overview",
    "account_profiles",
    "loss_run_upload",
    "claims_dashboard",
    "exposure_inputs",
    "ai_summary",
    "renewal_memo",
    "pdf_exports",
    "renewal_risk",
    "underwriter_decision",
    "carrier_appetite",
    "carrier_match",
    "submission_readiness",
    "premium_forecast",
    "submission_builder",
    "carrier_packet",
    "carrier_email_draft",
    "advanced_analytics",
    "audit_logs",
    "team_management",
    "user_permissions",
    "charts",

  ],
  founding_agency: [
    "overview",
    "account_profiles",
    "loss_run_upload",
    "claims_dashboard",
    "exposure_inputs",
    "ai_summary",
    "renewal_memo",
    "pdf_exports",
    "renewal_risk",
    "underwriter_decision",
    "carrier_appetite",
    "carrier_match",
    "submission_readiness",
    "premium_forecast",
    "submission_builder",
    "carrier_packet",
    "carrier_email_draft",
    "advanced_analytics",
    "audit_logs",
    "team_management",
    "user_permissions",
  ],
};

// LOSSQ_PROFESSIONAL_CHARTS_INCLUDED_V1
// LOSSQ_PROFESSIONAL_ADVANCED_ANALYTICS_INCLUDED_V1
// LOSSQ_PROFESSIONAL_AGENCY_CHARTS_ACCESS_V1
const LOSSQ_TOOL_REQUIRED_FEATURE: Record<string, string> = {
  overview: "overview",
  profiles: "account_profiles",
  upload: "loss_run_upload",
  "exposure-inputs": "exposure_inputs",
  claims: "claims_dashboard",
  summary: "ai_summary",
  memo: "renewal_memo",
  "renewal-risk": "renewal_risk",
  decision: "underwriter_decision",
  "carrier-appetite": "carrier_appetite",
  "carrier-match": "carrier_match",
  "submission-readiness": "submission_readiness",
  "premium-forecast": "premium_forecast",
  "submission-builder": "submission_builder",
  charts: "advanced_analytics",
};

const LOSSQ_FEATURE_LABELS: Record<string, string> = {
  renewal_risk: "Renewal Risk",
  underwriter_decision: "Underwriter Decision",
  carrier_appetite: "Carrier Appetite",
  carrier_match: "Carrier Match",
  submission_readiness: "Submission Readiness",
  premium_forecast: "Premium Forecast",
  submission_builder: "Submission Builder",
  carrier_packet: "Carrier Packet",
  carrier_email_draft: "Prepare Carrier Email",
  advanced_analytics: "Advanced Analytics",
  audit_logs: "Audit Logs",
  team_management: "Team Management",
  user_permissions: "User Permissions",
};



type AnyObject = Record<string, any>;

type ToolKey =
  | "overview"
  | "profiles"
  | "upload"
  | "exposure-inputs"
  | "renewal-risk"
  | "decision"
  | "carrier-appetite"
  | "submission-readiness"
  | "carrier-match"
  | "premium-forecast"
  | "submission-builder"
  | "summary"
  | "memo"
  | "charts"
  | "claims";

async function safeJson(res: Response) {
  try {
    return await res.json();
  } catch {
    return null;
  }
}

function objectToChartData(data: Record<string, number>) {
  return Object.entries(data || {}).map(([name, value]) => ({
    name,
    value: Number(value || 0),
  }));
}



function isBadPolicyNumberValue(value: any) {
  const cleaned = normalizePolicyNumber(value);

  if (!cleaned) return true;

  const badValues = new Set([
    "LINE-COVERAGE",
    "LINECOVERAGE",
    "POLICY",
    "POLICYNUMBER",
    "POLICY-NUMBER",
    "ACCOUNTNUMBER",
    "ACCOUNT-NUMBER",
    "EXPOSUREBASIS",
    "EXPOSURE-BASIS",
    "CURRENT-PREMIUM",
    "EXPIRING-PREMIUM",
    "TARGET-RENEWAL",
  ]);

  if (badValues.has(cleaned)) return true;

  if (cleaned.includes("COVERAGE") && !/\d/.test(cleaned)) return true;

  return false;
}

function chooseSafePolicyNumber(...values: any[]) {
  for (const value of values) {
    const cleaned = normalizePolicyNumber(value);
    if (cleaned && !isBadPolicyNumberValue(cleaned)) {
      return cleaned;
    }
  }

  return "";
}


function getEvaluationDateFromExpiration(expirationDate: any) {
  const raw = String(expirationDate || "").trim();

  if (!raw) return "";

  const parsed = new Date(raw);

  if (Number.isNaN(parsed.getTime())) return "";

  parsed.setMonth(parsed.getMonth() - 3);

  return parsed.toISOString().slice(0, 10);
}


function normalizeDateInput(value: any) {
  const raw = String(value || "").trim();

  if (!raw) return "";

  const isoMatch = raw.match(/\b((?:19|20)\d{2})[-/](\d{1,2})[-/](\d{1,2})\b/);
  if (isoMatch) {
    const [, yyyy, mm, dd] = isoMatch;
    return `${yyyy}-${String(Number(mm)).padStart(2, "0")}-${String(Number(dd)).padStart(2, "0")}`;
  }

  const usMatch = raw.match(/\b(\d{1,2})\/(\d{1,2})\/(\d{2,4})\b/);
  if (usMatch) {
    const [, mm, dd, yearValue] = usMatch;
    let yyyy = Number(yearValue);

    if (yyyy < 100) {
      yyyy += yyyy < 70 ? 2000 : 1900;
    }

    return `${yyyy}-${String(Number(mm)).padStart(2, "0")}-${String(Number(dd)).padStart(2, "0")}`;
  }

  return raw;
}

// LOSSQ_PREFER_UPLOAD_VALUATION_DATE_V1

// LOSSQ_UNIVERSAL_UPLOAD_DATE_MERGE_V1
function lossqFlatDateKey(value: any) {
  return String(value || "").trim().toLowerCase().replace(/[^a-z0-9]+/g, "");
}

function lossqUniversalDateKind(key: any) {
  const clean = lossqFlatDateKey(key);

  const effectiveKeys = new Set([
    "policyeffectivedate",
    "policyeffdate",
    "effectivedate",
    "effdate",
    "policyinceptiondate",
    "inceptiondate",
    "policyperiodstart",
    "periodstart",
  ]);

  const expirationKeys = new Set([
    "policyexpirationdate",
    "policyexpdate",
    "policyexpirydate",
    "expirationdate",
    "expdate",
    "expirydate",
    "policyperiodend",
    "periodend",
  ]);

  const valuationKeys = new Set([
    "valuationdate",
    "valuedate",
    "evaluationdate",
    "asofdate",
    "reportdate",
    "lossrunvaluationdate",
    "lossrunasofdate",
    "valuedasof",
    "valuedasofdate",
  ]);

  if (effectiveKeys.has(clean)) return "effective_date";
  if (expirationKeys.has(clean)) return "expiration_date";
  if (valuationKeys.has(clean)) return "valuation_date";

  if (clean.includes("effective") && clean.includes("date")) return "effective_date";
  if (clean.includes("expiration") && clean.includes("date")) return "expiration_date";
  if (clean.includes("expiry") && clean.includes("date")) return "expiration_date";
  if (clean.includes("valuation") && clean.includes("date")) return "valuation_date";
  if (clean.includes("evaluation") && clean.includes("date")) return "valuation_date";
  if (clean.includes("asof") && clean.includes("date")) return "valuation_date";

  return "";
}

function lossqScanUniversalUploadDates(value: any, found: any = {}) {
  if (!found.effective_date) found.effective_date = "";
  if (!found.expiration_date) found.expiration_date = "";
  if (!found.valuation_date) found.valuation_date = "";

  if (!value) return found;

  if (Array.isArray(value)) {
    value.forEach((item) => lossqScanUniversalUploadDates(item, found));
    return found;
  }

  if (typeof value === "object") {
    Object.entries(value).forEach(([key, item]) => {
      const kind = lossqUniversalDateKind(key);
      const cleanDate = normalizeDateInput(item);

      if (kind && cleanDate && !found[kind]) {
        found[kind] = cleanDate;
      }

      if (item && typeof item === "object") {
        lossqScanUniversalUploadDates(item, found);
      }
    });
  }

  return found;
}

function getUniversalUploadPolicyDates(...sources: any[]) {
  const found = {
    effective_date: "",
    expiration_date: "",
    valuation_date: "",
  };

  sources.forEach((source) => lossqScanUniversalUploadDates(source, found));

  return found;
}







// LOSSQ_EXACT_UPLOAD_DATE_FORCE_MERGE_V1
function lossqDateMergeValue(...values: any[]) {
  for (const value of values) {
    const clean = normalizeDateInput(value);
    if (clean) return clean;
  }
  return "";
}

function lossqForceDatesOntoPolicyRows(rows: any[], dateSource: any) {
  const sourceEffective = lossqDateMergeValue(
    dateSource?.effective_date,
    dateSource?.policy_effective_date,
    dateSource?.["Policy Effective Date"],
    dateSource?.["Effective Date"]
  );

  const sourceExpiration = lossqDateMergeValue(
    dateSource?.expiration_date,
    dateSource?.policy_expiration_date,
    dateSource?.["Policy Expiration Date"],
    dateSource?.["Expiration Date"]
  );

  const sourceValuation = lossqDateMergeValue(
    dateSource?.valuation_date,
    dateSource?.evaluation_date,
    dateSource?.loss_run_valuation_date,
    dateSource?.["Valuation Date"],
    dateSource?.["Evaluation Date"],
    dateSource?.["As Of Date"],
    dateSource?.["Report Date"]
  );

  return (Array.isArray(rows) ? rows : []).map((row: any) => {
    const rowEffective = lossqDateMergeValue(
      row?.effective_date,
      row?.policy_effective_date,
      row?.effectiveDate,
      row?.effective,
      row?.["Policy Effective Date"],
      row?.["Effective Date"],
      sourceEffective
    );

    const rowExpiration = lossqDateMergeValue(
      row?.expiration_date,
      row?.policy_expiration_date,
      row?.expirationDate,
      row?.expiration,
      row?.expiry_date,
      row?.["Policy Expiration Date"],
      row?.["Expiration Date"],
      sourceExpiration
    );

    const rowValuation = lossqDateMergeValue(
      row?.valuation_date,
      row?.evaluation_date,
      row?.loss_run_valuation_date,
      row?.["Valuation Date"],
      row?.["Evaluation Date"],
      row?.["As Of Date"],
      row?.["Report Date"],
      sourceValuation
    );

    return {
      ...(row || {}),
      effective_date: rowEffective,
      policy_effective_date: rowEffective,
      expiration_date: rowExpiration,
      policy_expiration_date: rowExpiration,
      valuation_date: rowValuation,
      evaluation_date: rowValuation,
      loss_run_valuation_date: rowValuation,
    };
  });
}


// LOSSQ_UNIVERSAL_EVALUATION_DATE_DISPLAY_V1
function lossqAnyEvaluationDate(row: any) {
  return normalizeDateInput(
    row?.evaluation_date ||
      row?.valuation_date ||
      row?.loss_run_valuation_date ||
      row?.valuationDate ||
      row?.["Evaluation Date"] ||
      row?.["Valuation Date"] ||
      row?.["As Of Date"] ||
      row?.["Report Date"] ||
      row?.as_of_date ||
      row?.report_date ||
      ""
  );
}

function lossqFirstPolicyEvaluationDate(rows: any[]) {
  return (Array.isArray(rows) ? rows : [])
    .map((row) => lossqAnyEvaluationDate(row))
    .find(Boolean) || "";
}


// LOSSQ_UNIVERSAL_DATE_DISPLAY_REPAIR_V1
function lossqAnyEffectiveDate(row: any) {
  return normalizeDateInput(
    row?.effective_date ||
      row?.policy_effective_date ||
      row?.policyEffectiveDate ||
      row?.["Policy Effective Date"] ||
      row?.["Effective Date"] ||
      row?.effective ||
      row?.eff_date ||
      row?.inception_date ||
      row?.policy_period_start ||
      ""
  );
}

function lossqAnyExpirationDate(row: any) {
  return normalizeDateInput(
    row?.expiration_date ||
      row?.policy_expiration_date ||
      row?.policyExpirationDate ||
      row?.["Policy Expiration Date"] ||
      row?.["Expiration Date"] ||
      row?.expiration ||
      row?.expiry_date ||
      row?.exp_date ||
      row?.policy_period_end ||
      ""
  );
}

function lossqFirstPolicyEffectiveDate(rows: any[]) {
  return (Array.isArray(rows) ? rows : [])
    .map((row) => lossqAnyEffectiveDate(row))
    .find(Boolean) || "";
}

function lossqFirstPolicyExpirationDate(rows: any[]) {
  return (Array.isArray(rows) ? rows : [])
    .map((row) => lossqAnyExpirationDate(row))
    .find(Boolean) || "";
}


// LOSSQ_STRICT_POLICY_SCHEDULE_DISPLAY_GATE_V1
function lossqStrictPolicyKey(value: any) {
  return String(value || "").toUpperCase().replace(/[^A-Z0-9]/g, "");
}

function lossqStrictText(value: any) {
  return String(value || "").replace(/\s+/g, " ").trim();
}

function lossqStrictPolicyNumber(row: any) {
  return lossqStrictText(
    row?.policy_number ||
      row?.policyNumber ||
      row?.policy_no ||
      row?.policy ||
      row?.main_policy ||
      ""
  );
}

function lossqStrictPolicyLine(row: any) {
  return lossqStrictText(
    row?.policy_type ||
      row?.line_of_business ||
      row?.line_coverage ||
      row?.coverage ||
      row?.line ||
      row?.lob ||
      ""
  );
}

function lossqStrictIsGenericLine(value: any) {
  const clean = lossqStrictText(value).toLowerCase();
  return ["", "policy", "policies", "coverage", "line", "line of business", "unknown", "n/a", "none", "-", "open", "closed", "pending"].includes(clean);
}

function lossqStrictDateLike(value: any) {
  const raw = lossqStrictText(value);
  return /\b(?:19|20)\d{2}[-/]\d{1,2}[-/]\d{1,2}\b/.test(raw) || /\b\d{1,2}\/\d{1,2}\/(?:\d{2}|\d{4})\b/.test(raw);
}

function lossqStrictMoneyLike(value: any) {
  return /^\(?\$?\s*\d[\d,]*(?:\.\d+)?\)?$/.test(lossqStrictText(value));
}

function lossqStrictLooksLikeClaimRow(row: any) {
  if (!row || typeof row !== "object") return false;

  const claimNumber = lossqStrictText(row?.claim_number || row?.claimNumber || row?.claim_no || row?.claim || row?.loss_number);
  const status = lossqStrictText(row?.status).toLowerCase();
  const cause = lossqStrictText(row?.cause_of_loss || row?.loss_description || row?.description);
  const paid = lossqStrictText(row?.paid || row?.paid_amount);
  const reserve = lossqStrictText(row?.reserve || row?.reserve_amount);

  return Boolean(
    claimNumber ||
      cause ||
      paid ||
      reserve ||
      ["open", "closed", "pending", "reopened", "reopen"].includes(status)
  );
}

function lossqStrictPolicyRowValid(row: any) {
  if (!row || typeof row !== "object") return false;
  if (lossqStrictLooksLikeClaimRow(row)) return false;

  const policyNumber = lossqStrictPolicyNumber(row);
  const policyKey = lossqStrictPolicyKey(policyNumber);
  const line = lossqStrictPolicyLine(row);

  if (!policyKey || policyKey.length < 8) return false;
  if (!/\d/.test(policyKey)) return false;
  if (lossqStrictIsGenericLine(line)) return false;
  if (lossqStrictDateLike(line) || lossqStrictMoneyLike(line)) return false;

  return true;
}

function lossqStrictCleanPolicySchedule(rows: any[]) {
  const sourceRows = Array.isArray(rows) ? rows : [];
  const validRows = sourceRows.filter(lossqStrictPolicyRowValid);

  const keys = validRows.map((row: any) => lossqStrictPolicyKey(lossqStrictPolicyNumber(row)));

  const filteredRows = validRows.filter((row: any) => {
    const key = lossqStrictPolicyKey(lossqStrictPolicyNumber(row));

    return !keys.some(
      (other: string) =>
        other !== key &&
        other.length > key.length &&
        (other.startsWith(key) || key.includes(other) || other.includes(key))
    );
  });

  const byKey: Record<string, any> = {};

  filteredRows.forEach((row: any) => {
    const key = lossqStrictPolicyKey(lossqStrictPolicyNumber(row));
    const line = lossqStrictPolicyLine(row);

    if (!key) return;

    byKey[key] = {
      ...(byKey[key] || {}),
      ...row,
      policy_number: lossqStrictPolicyNumber(row),
      policy_type: line,
      line_of_business: line,
      coverage: line,
    };
  });

  return Object.values(byKey);
}


// LOSSQ_UNIVERSAL_POLICY_SCHEDULE_CLEANUP_V1
function lossqCleanPolicyKey(value: any) {
  return String(value || "").toUpperCase().replace(/[^A-Z0-9]/g, "");
}

function lossqPolicyFamilyTokens(policyNumber: any) {
  return String(policyNumber || "")
    .toUpperCase()
    .split(/[^A-Z0-9]+/)
    .filter((token) => /[A-Z]/.test(token) && token.length >= 2);
}

function lossqLooksLikeClaimRow(row: any) {
  if (!row || typeof row !== "object") return false;

  const claimNumber = String(
    row?.claim_number ||
      row?.claimNumber ||
      row?.claim_no ||
      row?.claim ||
      row?.loss_number ||
      ""
  ).trim();

  const status = String(row?.status || "").trim().toLowerCase();
  const cause = String(row?.cause_of_loss || row?.loss_description || row?.description || "").trim();

  return Boolean(
    claimNumber ||
      cause ||
      ["open", "closed", "reopen", "reopened", "pending"].includes(status)
  );
}

function lossqPolicyNumberFromRow(row: any) {
  return String(
    row?.policy_number ||
      row?.policyNumber ||
      row?.policy_no ||
      row?.policy ||
      row?.main_policy ||
      ""
  ).trim();
}

function lossqPolicyLineFromRow(row: any) {
  return String(
    row?.policy_type ||
      row?.line_coverage ||
      row?.line_of_business ||
      row?.coverage ||
      row?.line ||
      row?.lob ||
      ""
  ).trim();
}

function lossqIsGenericPolicyLine(value: any) {
  const clean = String(value || "").trim().toLowerCase();
  return !clean || ["policy", "policies", "coverage", "line", "unknown", "n/a", "none", "-"].includes(clean);
}

function lossqCleanPolicyScheduleRows(rows: any[]) {
  const sourceRows = Array.isArray(rows) ? rows : [];
  const validRows = sourceRows.filter((row: any) => {
    if (!row || typeof row !== "object") return false;
    if (lossqLooksLikeClaimRow(row)) return false;

    const policyNumber = lossqPolicyNumberFromRow(row);
    const policyKey = lossqCleanPolicyKey(policyNumber);
    const line = lossqPolicyLineFromRow(row);

    return Boolean(policyKey && line && !lossqIsGenericPolicyLine(line));
  });

  const byKey: Record<string, any> = {};

  validRows.forEach((row: any) => {
    const policyNumber = lossqPolicyNumberFromRow(row);
    const key = lossqCleanPolicyKey(policyNumber);
    if (!key) return;

    const existingKey = Object.keys(byKey).find(
      (otherKey) =>
        otherKey === key ||
        otherKey.includes(key) ||
        key.includes(otherKey)
    );

    const targetKey =
      existingKey && existingKey.length >= key.length ? existingKey : key;

    const existing = existingKey ? byKey[existingKey] : undefined;

    const merged = {
      ...(existing || {}),
      ...row,
      policy_number:
        String(lossqPolicyNumberFromRow(existing || "")).length > String(policyNumber).length
          ? lossqPolicyNumberFromRow(existing)
          : policyNumber,
    };

    if (existingKey && targetKey !== existingKey) {
      delete byKey[existingKey];
    }

    byKey[targetKey] = merged;
  });

  return Object.values(byKey);
}


function getBestEvaluationDate(profileLike: any) {
  const explicitValuationDate = normalizeDateInput(
    profileLike?.valuation_date ||
      profileLike?.loss_run_valuation_date ||
      profileLike?.valuationDate ||
      profileLike?.lossRunValuationDate ||
      profileLike?.evaluation_date
  );

  if (explicitValuationDate) return explicitValuationDate;

  const derivedDate = getEvaluationDateFromExpiration(
    profileLike?.expiration_date ||
      profileLike?.policy_expiration_date ||
      profileLike?.expiry_date
  );

  return derivedDate || "";
}

function normalizePolicyNumber(value: any) {
  return String(value || "").trim().toUpperCase();
}

function getClaimPolicyNumber(claim: any) {
  return normalizePolicyNumber(
    claim?.policy_number ||
      claim?.policyNumber ||
      claim?.policy_no ||
      claim?.policy ||
      claim?.policy_id
  );
}

// LOSSQ_DEDUPE_VISIBLE_CLAIMS_V1
function getClaimDedupeKey(claim: any) {
  const claimNumber = normalizePolicyNumber(
    claim?.claim_number ||
      claim?.claimNumber ||
      claim?.claim_no ||
      claim?.claim_id ||
      claim?.id
  );

  const policyNumber = getClaimPolicyNumber(claim);

  const lossDate = String(
    claim?.date_of_loss ||
      claim?.loss_date ||
      claim?.dateOfLoss ||
      ""
  ).trim();

  const incurred = String(
    claim?.total_incurred ||
      claim?.incurred ||
      claim?.total ||
      ""
  ).trim();

  if (claimNumber && claimNumber !== "UNKNOWN") {
    return `${claimNumber}|${policyNumber || "NO-POLICY"}`;
  }

  return `${policyNumber}|${lossDate}|${incurred}`;
}

function dedupeClaims(claims: any[]) {
  const seen = new Set<string>();
  const next: any[] = [];

  (claims || []).forEach((claim) => {
    const key = getClaimDedupeKey(claim);
    if (!key || seen.has(key)) return;
    seen.add(key);
    next.push(claim);
  });

  return next;
}


function isOpenClaimStatus(claim: any) {
  const status = String(claim?.status || "").trim().toLowerCase();

  if (!status) return false;

  return [
    "open",
    "pending",
    "reopened",
    "active",
    "in progress",
    "watch",
  ].includes(status);
}

function toMoneyNumber(value: any) {
  if (value === null || value === undefined || value === "") return 0;

  const cleaned = String(value).replace(/[$,]/g, "").trim();
  const parsed = Number(cleaned);

  return Number.isFinite(parsed) ? parsed : 0;
}

function getClaimIncurred(claim: any) {
  const direct =
    claim?.total_incurred ??
    claim?.totalIncurred ??
    claim?.incurred ??
    claim?.incurred_amount ??
    claim?.loss_amount ??
    claim?.amount;

  const directValue = toMoneyNumber(direct);

  if (directValue > 0) return directValue;

  return (
    toMoneyNumber(claim?.paid_amount || claim?.paid || claim?.paid_loss) +
    toMoneyNumber(claim?.reserve_amount || claim?.reserve || claim?.outstanding_reserve)
  );
}

function normalizeProfiles(data: any): AnyObject[] {
  if (Array.isArray(data)) return data;
  if (Array.isArray(data?.profiles)) return data.profiles;
  if (Array.isArray(data?.accounts)) return data.accounts;
  if (data && typeof data === "object" && data.policy_number) return [data];
  return [];
}


// LOSSQ_PROFILE_SWITCH_CLEAN_RESET_V1
function looksLikeDateOnly(value: any) {
  const text = String(value || "").trim();
  return /^\d{4}-\d{2}-\d{2}$/.test(text) || /^\d{1,2}\/\d{1,2}\/\d{4}$/.test(text);
}

function looksLikeExposureText(value: any) {
  const text = String(value || "").toLowerCase();
  return /payroll|revenue|vehicles?|drivers?|employees?|limit|deductible|tiv|premium|expiration date|effective date|primary state/.test(text);
}

function looksLikeCarrierName(value: any) {
  const text = String(value || "").trim();
  if (!text || looksLikeDateOnly(text) || looksLikeExposureText(text)) return false;
  return /insurance|mutual|specialty|casualty|indemnity|underwriters|carrier|risk|group|national|state|commercial|berkley|zurich|travelers|hartford|liberty|carolina/i.test(text);
}

function cleanScheduleDate(value: any, fallback?: any) {
  // LOSSQ_POLICY_SCHEDULE_SMART_FALLBACK_V1
  const text = String(value || "").trim();
  const fallbackText = String(fallback || "").trim();

  if (looksLikeDateOnly(text)) return text;
  if (looksLikeDateOnly(fallbackText)) return fallbackText;

  return "-";
}

function cleanScheduleCarrier(value: any, fallback?: any) {
  const primary = String(value || "").trim();
  const secondary = String(fallback || "").trim();

  const primaryIsPartial =
    /^(specialty|commercial|mutual|insurance|carrier)$/i.test(primary) ||
    primary.length < 10;

  // Prefer the full account carrier if the row only has a partial word like "Specialty".
  if (looksLikeCarrierName(secondary) && (!looksLikeCarrierName(primary) || primaryIsPartial)) {
    return secondary;
  }

  if (looksLikeCarrierName(primary)) return primary;
  if (looksLikeCarrierName(secondary)) return secondary;

  return "-";
}

function cleanScheduleText(value: any) {
  const text = String(value || "").trim();
  if (!text) return "-";
  if (/expiration date|effective date|primary state/i.test(text)) return "-";
  return text;
}

function getUniversalIndustryLabel(profileLike: any, claimsLike: any[] = []) {
  const rawText = [
    profileLike?.business_name,
    profileLike?.line_of_business,
    profileLike?.industry,
    profileLike?.business_description,
    profileLike?.operations,
    profileLike?.class_code,
    profileLike?.class_codes,
    ...(Array.isArray(profileLike?.policies)
      ? profileLike.policies.map((p: any) => `${p?.line_of_business || ""} ${p?.policy_type || ""} ${p?.coverage || ""}`)
      : []),
    ...claimsLike.map((claim: any) => `${claim?.line_of_business || ""} ${claim?.claim_type || ""} ${claim?.description || ""} ${claim?.cause_of_loss || ""}`),
  ]
    .join(" ")
    .toLowerCase();

  if (/clean|janitor|facility|property maintenance|maintenance|repair|premises|building/.test(rawText)) {
    return "property maintenance, facility services, premises liability, and light repair operations";
  }

  if (/restaurant|food|hospitality/.test(rawText)) {
    return "hospitality and premises operations";
  }

  if (/contractor|construction|trade/.test(rawText)) {
    return "contractor and construction operations";
  }

  if (/truck|transport|fleet|auto|driver|vehicle/.test(rawText)) {
    return "commercial auto and fleet operations";
  }

  return "the account's actual business operations and coverage lines";
}

function resetProfileAnalyticsState(setters: any) {
  setters.setSummary?.({});
  setters.setDecision?.({});
  setters.setCarrierAppetite?.({});
  setters.setSubmissionReadiness?.({});
  setters.setCarrierMatch?.({});
  setters.setPremiumForecast?.({});
  setters.setSubmissionBuilder?.({});
  setters.setTimeline?.({});
  setters.setSelectedClaim?.(null);
  setters.setLazyLoadedTools?.({});
  setters.setLazyToolLoading?.({});
  clearCachedSelectedClaim();
}

function firstNonEmptyArray(...values: any[]) {
  for (const value of values) {
    if (Array.isArray(value) && value.length > 0) return value;
  }

  return [];
}

// LOSSQ_DERIVE_EXPOSURE_FROM_POLICY_ROWS_V3
// LOSSQ_EXPOSURE_EXTRACTOR_LABEL_STRICT_V3
function deriveExposureInputsFromPolicyRows(profileLike: any) {
  const exposure: AnyObject = {};

  const cleanValue = (value: any) =>
    String(value ?? "").replace(/\s+/g, " ").trim();

  const normalizeKey = (value: any) =>
    cleanValue(value).toLowerCase().replace(/[^a-z0-9]/g, "");

  const setIfBlank = (field: string, value: any) => {
    const clean = cleanValue(value);
    if (clean && !cleanValue(exposure[field])) {
      exposure[field] = clean;
    }
  };

  const isDateLike = (value: any) => {
    const raw = cleanValue(value);
    return (
      /^\d{4}[-/]\d{1,2}[-/]\d{1,2}$/.test(raw) ||
      /^\d{1,2}[-/]\d{1,2}[-/]\d{2,4}$/.test(raw) ||
      /^(19|20)\d{2}$/.test(raw)
    );
  };

  const cleanMoney = (value: any) => {
    const raw = cleanValue(value);
    if (!raw || isDateLike(raw)) return "";
    const match = raw.match(/\$?\s*[0-9][0-9,]*(?:\.\d{2})?/);
    if (!match) return "";
    const valueText = match[0].replace(/\s+/g, "");
    if (/^(19|20)\d{2}$/.test(valueText.replace(/[$,]/g, ""))) return "";
    return valueText;
  };

  const cleanCount = (value: any) => {
    const raw = cleanValue(value);
    if (!raw || isDateLike(raw)) return "";
    const match = raw.match(/\b[0-9][0-9,]*\b/);
    if (!match) return "";
    const valueText = match[0].replace(/,/g, "");
    if (/^(19|20)\d{2}$/.test(valueText)) return "";
    return valueText;
  };

  const fieldMap: Record<string, string> = {
    currentpremium: "current_premium",
    annualpremium: "current_premium",
    writtenpremium: "current_premium",
    totalpremium: "current_premium",
    premium: "current_premium",

    expiringpremium: "expiring_premium",
    priorpremium: "expiring_premium",
    previouspremium: "expiring_premium",

    targetrenewalpremium: "target_renewal_premium",
    renewalpremium: "target_renewal_premium",
    estimatedrenewalpremium: "target_renewal_premium",

    primarylineofbusiness: "line_of_business",
    lineofbusiness: "line_of_business",
    lob: "line_of_business",
    policytype: "line_of_business",
    coverage: "line_of_business",

    state: "state",
    primarystate: "state",

    classcode: "class_code",
    classcodes: "class_codes",

    policylimits: "limits",
    limits: "limits",
    coveragelimit: "coverage_limit",
    deductible: "deductible",
    retention: "retention",
    sir: "retention",

    payroll: "payroll",
    annualpayroll: "payroll",
    estimatedpayroll: "payroll",

    revenue: "revenue",
    annualrevenue: "revenue",
    sales: "sales",
    grosssales: "sales",
    receipts: "receipts",
    grossreceipts: "receipts",

    employeecount: "employee_count",
    employees: "employee_count",
    numberofemployees: "employee_count",

    vehiclecount: "vehicle_count",
    vehicles: "vehicle_count",
    powerunits: "vehicle_count",

    drivercount: "driver_count",
    drivers: "driver_count",

    propertytiv: "property_tiv",
    totalinsuredvalue: "property_tiv",
    tiv: "tiv",

    buildingvalue: "building_value",
    buildinglimit: "building_value",
    contentsvalue: "contents_value",
    businesspersonalproperty: "contents_value",
    bpp: "contents_value",

    squarefootage: "square_footage",
    sqft: "square_footage",
    locationcount: "location_count",
    locations: "location_count",
    unitcount: "unit_count",
    units: "unit_count",

    cargolimit: "cargo_limit",
    umbrellalimit: "umbrella_limit",
    excesslimit: "umbrella_limit",

    experiencemod: "experience_mod",
    mod: "mod",
    exposurechangepercent: "exposure_change_percent",
    cyberrevenue: "cyber_revenue",
    professionalrevenue: "professional_revenue",
    exposurebasis: "exposure_basis",
  };

  const moneyFields = new Set([
    "current_premium",
    "expiring_premium",
    "target_renewal_premium",
    "limits",
    "coverage_limit",
    "deductible",
    "retention",
    "payroll",
    "revenue",
    "sales",
    "receipts",
    "property_tiv",
    "tiv",
    "building_value",
    "contents_value",
    "cargo_limit",
    "umbrella_limit",
    "cyber_revenue",
    "professional_revenue",
  ]);

  const countFields = new Set([
    "employee_count",
    "vehicle_count",
    "driver_count",
    "square_footage",
    "location_count",
    "unit_count",
  ]);

  const applyMappedValue = (key: any, value: any) => {
    const mapped = fieldMap[normalizeKey(key)];
    if (!mapped) return;

    if (moneyFields.has(mapped)) {
      setIfBlank(mapped, cleanMoney(value));
      return;
    }

    if (countFields.has(mapped)) {
      setIfBlank(mapped, cleanCount(value));
      return;
    }

    setIfBlank(mapped, value);
  };

  const collectRows = (value: any): any[] => {
    if (!value) return [];
    if (Array.isArray(value)) return value;
    if (typeof value === "string") {
      try {
        const parsed = JSON.parse(value);
        return Array.isArray(parsed) ? parsed : [];
      } catch {
        return [];
      }
    }
    return [];
  };

  const localRows = (() => {
    if (typeof window === "undefined") return [];
    try {
      const cached = localStorage.getItem(CURRENT_UPLOAD_CACHE_KEY);
      const parsed = cached ? JSON.parse(cached) : null;
      if (Array.isArray(parsed)) return parsed;
      if (Array.isArray(parsed?.claims)) return parsed.claims;
      if (Array.isArray(parsed?.rows)) return parsed.rows;
      return [];
    } catch {
      return [];
    }
  })();

  const rows = [
    profileLike,
    profileLike?.validation,
    profileLike?.exposure_inputs,
    profileLike?.exposures,
    profileLike?.premium_worksheet,
    profileLike?.summary,
    ...collectRows(profileLike?.policies),
    ...collectRows(profileLike?.policy_schedule),
    ...collectRows(profileLike?.premium_worksheet),
    ...collectRows(profileLike?.exposures),
    ...collectRows(profileLike?.exposure_inputs),
    ...collectRows(profileLike?.validation?.policies),
    ...collectRows(profileLike?.validation?.policy_schedule),
    ...collectRows(profileLike?.validation?.premium_worksheet),
    ...collectRows(profileLike?.validation?.exposures),
    ...localRows,
  ].filter(Boolean);

  rows.forEach((row: any) => {
    if (!row || typeof row !== "object") return;

    Object.entries(row).forEach(([key, value]) => {
      applyMappedValue(key, value);
    });

    // Some upload rows may use display labels in one column and value in another.
    const label =
      row.label ||
      row.field ||
      row.metric ||
      row.name ||
      row.exposure_label ||
      row.exposure_type ||
      "";

    const value =
      row.value ||
      row.amount ||
      row.exposure_value ||
      row.exposure ||
      row.current_value ||
      row.manual_value ||
      "";

    if (label && value) {
      applyMappedValue(label, value);
    }
  });

  const labeledText = rows
    .map((row: any) => {
      if (!row || typeof row !== "object") return "";
      return Object.entries(row)
        .map(([key, value]) => `${key}: ${value}`)
        .join(" | ");
    })
    .join(" | ");

  const moneyAfter = (labels: string[]) => {
    for (const label of labels) {
      const pattern = new RegExp(`${label}[^$0-9]{0,50}(\\$?\\s*[0-9][0-9,]*(?:\\.\\d{2})?)`, "i");
      const match = labeledText.match(pattern);
      if (match) {
        const cleaned = cleanMoney(match[1]);
        if (cleaned) return cleaned;
      }
    }
    return "";
  };

  const countAfter = (labels: string[]) => {
    for (const label of labels) {
      const pattern = new RegExp(`${label}[^0-9]{0,50}([0-9][0-9,]*)`, "i");
      const match = labeledText.match(pattern);
      if (match) {
        const cleaned = cleanCount(match[1]);
        if (cleaned) return cleaned;
      }
    }
    return "";
  };

  setIfBlank("current_premium", moneyAfter(["current premium", "annual premium", "written premium", "total premium"]));
  setIfBlank("expiring_premium", moneyAfter(["expiring premium", "prior premium", "previous premium"]));
  setIfBlank("target_renewal_premium", moneyAfter(["target renewal premium", "renewal premium", "estimated renewal premium"]));
  setIfBlank("payroll", moneyAfter(["annual payroll", "estimated payroll", "payroll"]));
  setIfBlank("revenue", moneyAfter(["annual revenue", "gross sales", "revenue"]));
  setIfBlank("sales", moneyAfter(["gross sales", "sales"]));
  setIfBlank("receipts", moneyAfter(["gross receipts", "receipts"]));
  setIfBlank("property_tiv", moneyAfter(["property tiv", "total insured value"]));
  setIfBlank("tiv", moneyAfter(["total insured value", "tiv"]));
  setIfBlank("coverage_limit", moneyAfter(["coverage limit", "policy limit"]));
  setIfBlank("limits", moneyAfter(["policy limits", "coverage limit"]));
  setIfBlank("deductible", moneyAfter(["deductible"]));
  setIfBlank("umbrella_limit", moneyAfter(["umbrella limit", "excess limit"]));
  setIfBlank("cyber_revenue", moneyAfter(["cyber revenue"]));
  setIfBlank("professional_revenue", moneyAfter(["professional revenue"]));

  setIfBlank("employee_count", countAfter(["employee count", "number of employees", "employees"]));
  setIfBlank("vehicle_count", countAfter(["vehicle count", "vehicles", "power units"]));
  setIfBlank("driver_count", countAfter(["driver count", "drivers"]));
  setIfBlank("location_count", countAfter(["location count", "locations"]));
  setIfBlank("unit_count", countAfter(["unit count", "units"]));
  setIfBlank("square_footage", countAfter(["square footage", "sq ft", "sqft"]));
  // Primary Line of Business is manual-only in Exposure Inputs.
  const basisParts = [
    exposure.payroll ? `Payroll: ${exposure.payroll}` : "",
    exposure.revenue ? `Revenue: ${exposure.revenue}` : "",
    exposure.vehicle_count ? `Vehicles: ${exposure.vehicle_count}` : "",
    exposure.driver_count ? `Drivers: ${exposure.driver_count}` : "",
    exposure.employee_count ? `Employees: ${exposure.employee_count}` : "",
    exposure.property_tiv ? `Property TIV: ${exposure.property_tiv}` : "",
    exposure.coverage_limit ? `Limit: ${exposure.coverage_limit}` : "",
  ].filter(Boolean);

  if (basisParts.length > 0) {
    setIfBlank("exposure_basis", basisParts.join(" | "));
  }

  delete exposure.line_of_business;
  delete exposure.primary_line_of_business;
  delete exposure.class_code;
  delete exposure.class_codes;
  delete exposure.state;

  return exposure;
}

function cleanPolicyScheduleDisplayValue(value: any, kind?: "date" | "carrier") {
  const text = String(value || "").trim();

  if (!text) return "-";

  if (kind === "date") {
    if (/^\d{4}-\d{2}-\d{2}$/.test(text)) return text;
    if (/^\d{2}\/\d{2}\/\d{4}$/.test(text)) return text;
    return "-";
  }

  if (kind === "carrier") {
    if (/payroll|revenue|vehicles|drivers|limit|deductible|tiv|employee/i.test(text)) {
      return "-";
    }
  }

  return text;
}

function getCachedProfiles(): AnyObject[] {
  if (typeof window === "undefined") return [];

  try {
    const raw = localStorage.getItem(PROFILE_CACHE_KEY);
    const parsed = raw ? JSON.parse(raw) : [];
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

function setCachedProfiles(profiles: AnyObject[]) {
  if (typeof window === "undefined") return;
  localStorage.setItem(PROFILE_CACHE_KEY, JSON.stringify(profiles));
}


function getCachedSelectedPolicy() {
  if (typeof window === "undefined") return "";
  return normalizePolicyNumber(localStorage.getItem(SELECTED_POLICY_CACHE_KEY));
}

function setCachedSelectedPolicy(policyNumber: any) {
  if (typeof window === "undefined") return;

  const normalized = normalizePolicyNumber(policyNumber);

  if (normalized) {
    localStorage.setItem(SELECTED_POLICY_CACHE_KEY, normalized);
  }
}

function clearCachedSelectedPolicy() {
  if (typeof window === "undefined") return;
  localStorage.removeItem(SELECTED_POLICY_CACHE_KEY);
}

function getCachedSelectedClaim(): AnyObject | null {
  if (typeof window === "undefined") return null;

  try {
    const raw =
      sessionStorage.getItem(SELECTED_CLAIM_CACHE_KEY) ||
      localStorage.getItem(SELECTED_CLAIM_CACHE_KEY);

    const parsed = raw ? JSON.parse(raw) : null;
    return parsed && typeof parsed === "object" ? parsed : null;
  } catch {
    return null;
  }
}

function setCachedSelectedClaim(claim: AnyObject) {
  if (typeof window === "undefined") return;

  if (claim && typeof claim === "object") {
    const value = JSON.stringify(claim);
    sessionStorage.setItem(SELECTED_CLAIM_CACHE_KEY, value);
    localStorage.setItem(SELECTED_CLAIM_CACHE_KEY, value);
  }
}

function clearCachedSelectedClaim() {
  if (typeof window === "undefined") return;

  sessionStorage.removeItem(SELECTED_CLAIM_CACHE_KEY);
  localStorage.removeItem(SELECTED_CLAIM_CACHE_KEY);
}


function getCachedLastUploadReview(): AnyObject {
  if (typeof window === "undefined") return {};

  try {
    const raw = localStorage.getItem("lossq_last_upload_review");
    const parsed = raw ? JSON.parse(raw) : {};
    return parsed && typeof parsed === "object" ? parsed : {};
  } catch {
    return {};
  }
}

function clearCachedLastUploadReview() {
  if (typeof window === "undefined") return;
  localStorage.removeItem("lossq_last_upload_review");
}

function getCachedCurrentUpload(): AnyObject {
  if (typeof window === "undefined") return {};

  try {
    const raw = localStorage.getItem(CURRENT_UPLOAD_CACHE_KEY);
    const parsed = raw ? JSON.parse(raw) : {};
    return parsed && typeof parsed === "object" ? parsed : {};
  } catch {
    return {};
  }
}

function setCachedCurrentUpload(upload: AnyObject) {
  if (typeof window === "undefined") return;
  localStorage.setItem(CURRENT_UPLOAD_CACHE_KEY, JSON.stringify(upload || {}));
}

function clearCachedCurrentUpload() {
  if (typeof window === "undefined") return;
  localStorage.removeItem(CURRENT_UPLOAD_CACHE_KEY);
}

// LOSSQ_STRICT_SELECTED_PROFILE_CLAIMS_V1
function claimMatchesPolicySet(claim: any, policySet: Set<string>) {
  if (!policySet || policySet.size === 0) return false;

  // LOSSQ_ACCOUNT_LEVEL_CLAIM_MATCH_V1
  // Match both child policy claims and account-level claims.
  // Some uploaded loss runs normalize duplicate/worksheet rows to the account key,
  // while other rows retain the child policy number.
  const possibleClaimKeys = [
    getClaimPolicyNumber(claim),
    claim?.account_number,
    claim?.accountNumber,
    claim?.customer_number,
    claim?.customerNumber,
    claim?.profile_policy_number,
    claim?.selected_policy_number,
  ]
    .map((item: any) => normalizePolicyNumber(item))
    .filter(Boolean);

  return possibleClaimKeys.some((key) => policySet.has(key));
}

function mergeClaimsByNumber(existing: any[], incoming: any[]) {
  const map = new Map<string, any>();

  [...existing, ...incoming].forEach((claim) => {
    const key = `${claim?.claim_number || claim?.claimNumber || claim?.id || Math.random()}-${getClaimPolicyNumber(claim)}`;
    map.set(key, claim);
  });

  return Array.from(map.values());
}

function getClaimNumberValue(claim: any) {
  return String(claim?.claim_number || claim?.claimNumber || claim?.number || "").trim().toUpperCase();
}

function sameClaimRecord(a: any, b: any) {
  return (
    getClaimNumberValue(a) &&
    getClaimNumberValue(a) === getClaimNumberValue(b) &&
    getClaimPolicyNumber(a) === getClaimPolicyNumber(b)
  );
}


function cleanMoneyInput(value: any) {
  return String(value || "")
    .replace(/[^0-9.\-]/g, "")
    .trim();
}

function findTextValue(rawText: string, labels: string[]) {
  const text = String(rawText || "");
  const lines = text
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean);

  for (const label of labels) {
    const safe = label.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    const inline = new RegExp(`${safe}\\s*[:=\\-]?\\s*([^\\n\\r|]+)`, "i");
    const inlineMatch = text.match(inline);
    if (inlineMatch?.[1]) {
      const value = inlineMatch[1].trim();
      if (value && value.length < 120) return value;
    }

    const lineIndex = lines.findIndex((line) =>
      line.toLowerCase().includes(label.toLowerCase())
    );

    if (lineIndex >= 0 && lines[lineIndex + 1]) {
      const value = lines[lineIndex + 1].trim();
      if (value && value.length < 120) return value;
    }
  }

  return "";
}

function extractExposureInputsFromUploadText(rawText: string) {
  const text = String(rawText || "");

  if (!text.trim()) return {};

  const exposure: AnyObject = {
    current_premium: cleanMoneyInput(
      findTextValue(text, [
        "Current Premium",
        "Expiring Premium",
        "Annual Premium",
        "Premium",
      ])
    ),
    expiring_premium: cleanMoneyInput(
      findTextValue(text, [
        "Expiring Premium",
        "Prior Premium",
        "Current Term Premium",
      ])
    ),
    target_renewal_premium: cleanMoneyInput(
      findTextValue(text, [
        "Target Renewal Premium",
        "Target Premium",
        "Renewal Target",
      ])
    ),
    exposure_basis:
      findTextValue(text, [
        "Exposure Basis",
        "Rating Basis",
        "Premium Basis",
      ]) || "",
    payroll: cleanMoneyInput(
      findTextValue(text, [
        "Payroll",
        "Estimated Payroll",
        "Annual Payroll",
      ])
    ),
    revenue: cleanMoneyInput(
      findTextValue(text, [
        "Revenue",
        "Sales",
        "Gross Sales",
        "Annual Revenue",
        "Receipts",
      ])
    ),
    sales: cleanMoneyInput(
      findTextValue(text, [
        "Sales",
        "Gross Sales",
      ])
    ),
    receipts: cleanMoneyInput(
      findTextValue(text, [
        "Receipts",
        "Gross Receipts",
      ])
    ),
    employee_count:
      findTextValue(text, [
        "Employee Count",
        "Employees",
        "Number of Employees",
      ]) || "",
    vehicle_count:
      findTextValue(text, [
        "Vehicle Count",
        "Power Units",
        "Autos",
        "Scheduled Autos",
      ]) || "",
    driver_count:
      findTextValue(text, [
        "Driver Count",
        "Drivers",
        "Number of Drivers",
      ]) || "",
    property_tiv: cleanMoneyInput(
      findTextValue(text, [
        "Property TIV",
        "TIV",
        "Total Insured Value",
      ])
    ),
    tiv: cleanMoneyInput(
      findTextValue(text, [
        "TIV",
        "Total Insured Value",
      ])
    ),
    building_value: cleanMoneyInput(
      findTextValue(text, [
        "Building Value",
        "Building Limit",
      ])
    ),
    contents_value: cleanMoneyInput(
      findTextValue(text, [
        "Contents Value",
        "Business Personal Property",
        "BPP",
      ])
    ),
    square_footage:
      findTextValue(text, [
        "Square Footage",
        "Sq Ft",
        "Sq. Ft.",
      ]) || "",
    location_count:
      findTextValue(text, [
        "Location Count",
        "Locations",
        "Number of Locations",
      ]) || "",
    unit_count:
      findTextValue(text, [
        "Unit Count",
        "Units",
      ]) || "",
    class_code:
      findTextValue(text, [
        "Class Code",
        "Class Codes",
        "WC Code",
        "GL Class",
      ]) || "",
    class_codes:
      findTextValue(text, [
        "Class Codes",
        "Class Code",
        "WC Code",
        "GL Class",
      ]) || "",
    limits:
      findTextValue(text, [
        "Policy Limits",
        "Limits",
        "Coverage Limit",
      ]) || "",
    coverage_limit:
      findTextValue(text, [
        "Coverage Limit",
        "Policy Limits",
        "Limits",
      ]) || "",
    deductible:
      findTextValue(text, [
        "Deductible",
      ]) || "",
    retention:
      findTextValue(text, [
        "Retention",
        "SIR",
        "Self Insured Retention",
      ]) || "",
    cargo_limit:
      findTextValue(text, [
        "Cargo Limit",
        "Motor Truck Cargo Limit",
      ]) || "",
    umbrella_limit:
      findTextValue(text, [
        "Umbrella Limit",
        "Excess Limit",
        "Umbrella / Excess Limit",
      ]) || "",
    experience_mod:
      findTextValue(text, [
        "Experience Mod",
        "Experience Modification",
        "E-Mod",
        "Mod",
      ]) || "",
    mod:
      findTextValue(text, [
        "Experience Mod",
        "E-Mod",
        "Mod",
      ]) || "",
    exposure_change_percent:
      findTextValue(text, [
        "Exposure Change %",
        "Exposure Change",
        "Projected Change",
      ]) || "",
  };

  Object.keys(exposure).forEach((key) => {
    if (exposure[key] === "" || exposure[key] === null || exposure[key] === undefined) {
      delete exposure[key];
    }
  });

  return exposure;
}

function isBadCarrierValue(value: any) {
  const text = String(value || "").trim().toLowerCase();

  if (!text) return true;

  return [
    "exposure basis",
    "premium worksheet",
    "rating basis",
    "current premium",
    "expiring premium",
    "line coverage",
    "line-of-business",
    "line of business",
    "policy schedule",
    "coverage schedule",
    "carrier",
    "writing carrier",
  ].includes(text);
}

function chooseCleanCarrier(...values: any[]) {
  for (const value of values) {
    const cleaned = String(value || "").trim();
    if (cleaned && !isBadCarrierValue(cleaned)) return cleaned;
  }

  return "";
}

function mergeProfiles(existing: AnyObject[], incoming: AnyObject[]) {
  const map = new Map<string, AnyObject>();

  existing.forEach((item) => {
    const key = item?.policy_number || item?.id;
    if (key) map.set(String(key), item);
  });

  incoming.forEach((item) => {
    const key = item?.policy_number || item?.id;
    if (key) {
      map.set(String(key), {
        ...(map.get(String(key)) || {}),
        ...item,
      });
    }
  });

  return Array.from(map.values());
}




// LOSSQ_FRONTEND_ACCOUNT_NUMBER_POLICY_SANITIZER_V1
function lossqLooksLikePolicyNumber(value: any): boolean {
  const text = String(value || "").trim().toUpperCase();
  if (!text) return false;
  return /\b[A-Z]{1,8}[- ]?\d{2,6}[- ]?[A-Z0-9]{2,12}\b/.test(text);
}

function lossqCleanAccountNumber(value: any): string {
  const text = String(value || "").trim();
  if (!text) return "";
  return lossqLooksLikePolicyNumber(text) ? "" : text;
}



// LOSSQ_FRONTEND_ACCOUNT_NUMBER_DISPLAY_ONLY_REAL_ACCOUNT_V1
function lossqDisplayAccountNumber(profileLike: any): string {
  const accountNumber = lossqCleanAccountNumber(profileLike?.account_number);
  const customerNumber = lossqCleanAccountNumber(profileLike?.customer_number);

  return accountNumber || customerNumber || "";
}

function clearDeletedProfileBrowserTraces(profileToDelete: any) {
  // LOSSQ_HARD_DELETE_BROWSER_TRACES_V1
  // When a profile/file is deleted, remove every browser-side trace that can rehydrate it.
  if (typeof window === "undefined") return;

  const deleteKeys = [
    normalizePolicyNumber(profileToDelete?.policy_number),
    normalizePolicyNumber(profileToDelete?.account_number),
    normalizePolicyNumber(profileToDelete?.customer_number),
    ...(Array.isArray(profileToDelete?.policies)
      ? profileToDelete.policies.map((p: any) => normalizePolicyNumber(p?.policy_number))
      : []),
  ].filter(Boolean);

  const profileText = JSON.stringify(profileToDelete || "").toLowerCase();

  const shouldRemoveObject = (item: any) => {
    const itemKeys = [
      normalizePolicyNumber(item?.policy_number),
      normalizePolicyNumber(item?.account_number),
      normalizePolicyNumber(item?.customer_number),
      ...(Array.isArray(item?.policies)
        ? item.policies.map((p: any) => normalizePolicyNumber(p?.policy_number))
        : []),
    ].filter(Boolean);

    const itemText = JSON.stringify(item || "").toLowerCase();

    const keyMatch = itemKeys.some((key: string) => deleteKeys.includes(key));

    return keyMatch;
  };

  try {
    const cachedProfiles = JSON.parse(localStorage.getItem(PROFILE_CACHE_KEY) || "[]");
    if (Array.isArray(cachedProfiles)) {
      const nextProfiles = cachedProfiles.filter((item: any) => !shouldRemoveObject(item));
      localStorage.setItem(PROFILE_CACHE_KEY, JSON.stringify(nextProfiles));
    }
  } catch {
    localStorage.removeItem(PROFILE_CACHE_KEY);
  }

  try {
    const selectedPolicy = normalizePolicyNumber(localStorage.getItem(SELECTED_POLICY_CACHE_KEY));
    if (selectedPolicy && deleteKeys.includes(selectedPolicy)) {
      localStorage.removeItem(SELECTED_POLICY_CACHE_KEY);
    }
  } catch {
    localStorage.removeItem(SELECTED_POLICY_CACHE_KEY);
  }

  // Upload snapshots are intentionally cleared fully.
  // They are temporary parsing state and should never survive a delete.
  localStorage.removeItem(CURRENT_UPLOAD_CACHE_KEY);
  localStorage.removeItem(SELECTED_CLAIM_CACHE_KEY);
  localStorage.removeItem("lossq_last_upload_review");

  // Do not clear all sessionStorage here.
  // It contains lossq_tab_token, and clearing it logs the user out before DELETE finishes.
  sessionStorage.removeItem("lossq_welcome");
  sessionStorage.removeItem("lossq_welcome_name");
}



// LOSSQ_CLEAR_DASHBOARD_TENANT_CACHE_V1
function clearLossQDashboardTenantCache() {
  if (typeof window === "undefined") return;

  const shouldClear = (key: string) => {
    const clean = String(key || "").toLowerCase();

    return (
      clean.includes("claim") ||
      clean.includes("claims") ||
      clean.includes("profile") ||
      clean.includes("account") ||
      clean.includes("dashboard") ||
      clean.includes("carrier") ||
      clean.includes("renewal")
    );
  };

  Object.keys(localStorage).forEach((key) => {
    if (shouldClear(key) && key !== "lossq_token") {
      localStorage.removeItem(key);
    }
  });

  Object.keys(sessionStorage).forEach((key) => {
    if (shouldClear(key)) {
      sessionStorage.removeItem(key);
    }
  });
}




// LOSSQ_EXTRACTION_REVIEW_BANNER_V1
function lossqExtractionQualityFromProfile(profile: any) {
  const quality =
    profile?.extraction_quality ||
    profile?.validation?.extraction_quality ||
    profile?.validation?.quality ||
    null;

  const score =
    quality?.score ??
    profile?.extraction_score ??
    profile?.validation?.extraction_score ??
    null;

  const status =
    quality?.status ||
    profile?.extraction_status ||
    profile?.validation?.extraction_status ||
    "";

  const warnings =
    quality?.warnings ||
    profile?.validation?.extraction_warnings ||
    [];

  const criticalIssues =
    quality?.critical_issues ||
    profile?.validation?.extraction_critical_issues ||
    [];

  const requiresReview =
    Boolean(
      quality?.requires_review ||
      profile?.requires_review ||
      profile?.validation?.requires_review ||
      status === "review_required"
    );

  return {
    quality,
    score,
    status,
    warnings: Array.isArray(warnings) ? warnings : [],
    criticalIssues: Array.isArray(criticalIssues) ? criticalIssues : [],
    requiresReview,
  };
}

function LossQExtractionReviewBanner({ profile }: { profile: any }) {
  const { score, status, warnings, criticalIssues, requiresReview } =
    lossqExtractionQualityFromProfile(profile);

  if (
    score === null &&
    !status &&
    warnings.length === 0 &&
    criticalIssues.length === 0
  ) {
    return null;
  }

  const isCritical = requiresReview || status === "review_required";
  const isWarning = !isCritical && (status === "needs_attention" || warnings.length > 0);

  const title = isCritical
    ? "Review Required Before Relying on This Extraction"
    : isWarning
      ? "Extraction Needs Attention"
      : "Extraction Passed Quality Checks";

  const scoreLabel = score === null || score === undefined ? "Not scored" : `${score}/100`;

  const boxClass = isCritical
    ? "border-red-400/40 bg-red-500/10 text-red-100"
    : isWarning
      ? "border-amber-400/40 bg-amber-500/10 text-amber-100"
      : "border-emerald-400/40 bg-emerald-500/10 text-emerald-100";

  return (
    <div className={`mb-6 rounded-2xl border p-5 shadow-xl ${boxClass}`}>
      <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
        <div>
          <p className="text-sm font-bold uppercase tracking-[0.2em] opacity-80">
            LossQ Extraction QA
          </p>
          <h3 className="mt-1 text-xl font-black">{title}</h3>
          <p className="mt-2 text-sm opacity-90">
            Extraction score: <span className="font-bold">{scoreLabel}</span>
          </p>
        </div>

        <div className="rounded-xl border border-white/10 bg-black/20 px-4 py-3 text-sm font-bold">
          Status: {status ? String(status).replaceAll("_", " ").toUpperCase() : "CHECKED"}
        </div>
      </div>

      {(criticalIssues.length > 0 || warnings.length > 0) && (
        <div className="mt-4 grid gap-3 md:grid-cols-2">
          {criticalIssues.length > 0 && (
            <div className="rounded-xl border border-white/10 bg-black/20 p-4">
              <p className="mb-2 text-sm font-bold">Critical Issues</p>
              <ul className="list-disc space-y-1 pl-5 text-sm">
                {criticalIssues.map((item: string, index: number) => (
                  <li key={`critical-${index}`}>{item}</li>
                ))}
              </ul>
            </div>
          )}

          {warnings.length > 0 && (
            <div className="rounded-xl border border-white/10 bg-black/20 p-4">
              <p className="mb-2 text-sm font-bold">Warnings</p>
              <ul className="list-disc space-y-1 pl-5 text-sm">
                {warnings.map((item: string, index: number) => (
                  <li key={`warning-${index}`}>{item}</li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}

      {isCritical && (
        <p className="mt-4 text-sm font-semibold opacity-90">
          Do not submit this account to a carrier until policy dates, policy numbers,
          claim numbers, and claim totals are reviewed.
        </p>
      )}
    </div>
  );
}




// LOSSQ_FRONTEND_BETA_GUARDRAILS_V1
function lossqCleanText(value: unknown): string {
  return String(value ?? "").replace(/\s+/g, " ").trim();
}

function lossqUpper(value: unknown): string {
  return lossqCleanText(value).toUpperCase();
}

function lossqLooksLikeRealClaim(value: unknown): boolean {
  const claimNumber = lossqUpper(value);

  if (!claimNumber) return false;

  const blockedExact = new Set([
    "NOTE",
    "NOTES",
    "METRIC",
    "VALUE",
    "FIELD",
    "LOSS SUMMARY",
    "UNDERWRITING NOTES",
    "TOTAL CLAIMS",
    "OPEN CLAIMS",
    "CLOSED CLAIMS",
    "TOTAL PAID",
    "TOTAL RESERVE",
    "TOTAL INCURRED",
    "LARGEST LOSS",
    "LOSS RATIO",
    "CURRENT PREMIUM",
    "EXPIRING PREMIUM",
    "TARGET RENEWAL PREMIUM",
    "PAYROLL",
    "REVENUE / SALES",
    "EMPLOYEE COUNT",
    "VEHICLE COUNT",
    "DRIVER COUNT",
    "PROPERTY TIV",
    "POLICY SCHEDULE",
    "EXPOSURE INPUTS",
    "ACCOUNT INFORMATION",
  ]);

  if (blockedExact.has(claimNumber)) return false;

  const blockedContains = [
    "FICTIONAL TEST",
    "DESIGNED TO TEST",
    "NOT AFFILIATED",
    "LOSS SUMMARY",
    "UNDERWRITING NOTES",
    "EXPOSURE INPUTS",
    "POLICY SCHEDULE",
    "ACCOUNT INFORMATION",
  ];

  if (blockedContains.some((item) => claimNumber.includes(item))) return false;

  if (!/\d/.test(claimNumber)) return false;

  return /[A-Z0-9]+[-_][A-Z0-9]+[-_]\d{2,4}[-_]\d{2,6}/.test(claimNumber)
    || /(CLM|CLAIM|GL|WC|AUTO|AU|PROP|PR|CP|CPL|PROPERTY|CY|BOP|UMB|CARGO|MTC|EPLI|DO|DNO|LIAB|LIQUOR|PL|PROF|PROFESSIONAL|GAR|GARAGE|GARAGEKEEPERS|ABUSE|MOLESTATION|SAM|SML|AANDM|SEXUAL|MISCONDUCT|SPECIALTY|CARE|DAYCARE)/.test(claimNumber);
}

function lossqClaimNumberFromRow(row: any): string {
  return lossqCleanText(
    row?.claim_number
    ?? row?.claimNumber
    ?? row?.claim_no
    ?? row?.claim
    ?? row?.claim_id
    ?? ""
  );
}

// LOSSQ_FRONTEND_CLAIM_FILTER_ACTIVE_V1
function lossqFilterRealClaims<T = any>(rows: T[]): T[] {
  if (!Array.isArray(rows)) return [];

  return rows.filter((row: any) => {
    const claimNumber = lossqClaimNumberFromRow(row);
    return lossqLooksLikeRealClaim(claimNumber);
  });
}

function lossqDateValue(...values: unknown[]): string {
  for (const value of values) {
    const raw = lossqCleanText(value);
    if (!raw || raw === "-" || raw.toLowerCase() === "not set") continue;
    return raw;
  }
  return "";
}

function lossqFormatDateSafe(...values: unknown[]): string {
  const raw = lossqDateValue(...values);
  if (!raw) return "Not set";

  const normalized = raw.replace(/\\/g, "/").replace(/\./g, "/").replace(/-/g, "/").trim();

  const mdy = normalized.match(/^(\d{1,2})\/(\d{1,2})\/(\d{2,4})$/);
  if (mdy) {
    const month = Number(mdy[1]);
    const day = Number(mdy[2]);
    let year = Number(mdy[3]);
    if (year < 100) year += year < 50 ? 2000 : 1900;
    if (month >= 1 && month <= 12 && day >= 1 && day <= 31) {
      return `${String(month).padStart(2, "0")}/${String(day).padStart(2, "0")}/${year}`;
    }
  }

  const ymd = normalized.match(/^(\d{4})\/(\d{1,2})\/(\d{1,2})$/);
  if (ymd) {
    const year = Number(ymd[1]);
    const month = Number(ymd[2]);
    const day = Number(ymd[3]);
    if (month >= 1 && month <= 12 && day >= 1 && day <= 31) {
      return `${String(month).padStart(2, "0")}/${String(day).padStart(2, "0")}/${year}`;
    }
  }

  return raw;
}

function lossqHumanUploadError(error: any): string {
  const detail = error?.detail ?? error?.message ?? error;

  if (typeof detail === "object" && detail !== null) {
    const message = detail.message || detail.error || detail.stage;
    if (message) return String(message);
  }

  const text = lossqCleanText(detail);

  if (!text || text.toLowerCase().includes("failed to fetch")) {
    return "Upload failed before completion. The backend may be redeploying, offline, or rejected the file. Check that /docs loads, then try again.";
  }

  return text;
}




// LOSSQ_EVALUATION_DATE_ALERT_BADGE_V1
// LOSSQ_EVALUATION_DATE_ALERT_RENDER_V1
function lossqParseDateForAge(value: unknown): Date | null {
  const raw = lossqCleanText(value);
  if (!raw || raw === "-" || raw.toLowerCase() === "not set") return null;

  const normalized = raw.replace(/\\/g, "/").replace(/\./g, "/").replace(/-/g, "/").trim();

  const mdy = normalized.match(/^(\d{1,2})\/(\d{1,2})\/(\d{2,4})$/);
  if (mdy) {
    const month = Number(mdy[1]);
    const day = Number(mdy[2]);
    let year = Number(mdy[3]);
    if (year < 100) year += year < 50 ? 2000 : 1900;
    const date = new Date(year, month - 1, day);
    return Number.isNaN(date.getTime()) ? null : date;
  }

  const ymd = normalized.match(/^(\d{4})\/(\d{1,2})\/(\d{1,2})$/);
  if (ymd) {
    const year = Number(ymd[1]);
    const month = Number(ymd[2]);
    const day = Number(ymd[3]);
    const date = new Date(year, month - 1, day);
    return Number.isNaN(date.getTime()) ? null : date;
  }

  const fallback = new Date(raw);
  return Number.isNaN(fallback.getTime()) ? null : fallback;
}

function lossqEvaluationDateRaw(profileLike: any, policyRows: any[] = []): string {
  return lossqFirstValue(
    profileLike?.evaluation_date,
    profileLike?.valuation_date,
    profileLike?.loss_run_valuation_date,
    profileLike?.as_of_date,
    profileLike?.report_date,
    profileLike?.["Evaluation Date"],
    profileLike?.["Valuation Date"],
    profileLike?.["As Of Date"],
    profileLike?.["Report Date"],
    lossqFirstPolicyEvaluationDate(policyRows)
  );
}

function lossqEvaluationDateAgeDays(profileLike: any, policyRows: any[] = []): number | null {
  const raw = lossqEvaluationDateRaw(profileLike, policyRows);
  const parsed = lossqParseDateForAge(raw);
  if (!parsed) return null;

  const today = new Date();
  const start = new Date(parsed.getFullYear(), parsed.getMonth(), parsed.getDate()).getTime();
  const end = new Date(today.getFullYear(), today.getMonth(), today.getDate()).getTime();

  return Math.floor((end - start) / (1000 * 60 * 60 * 24));
}

function lossqBestPolicyExpirationDateRaw(profileLike: any, policyRows: any[] = []): any {
  const profileDate = lossqFirstValue(
    profileLike?.expiration_date,
    profileLike?.policy_expiration_date,
    profileLike?.expiry_date,
    profileLike?.expiration,
    profileLike?.expirationDate,
    profileLike?.policyExpirationDate,
    profileLike?.["Expiration Date"],
    profileLike?.["Policy Expiration Date"]
  );

  if (profileDate) return profileDate;

  const rows = Array.isArray(policyRows) ? policyRows : [];
  for (const row of rows) {
    const rowDate = lossqFirstValue(
      row?.expiration_date,
      row?.policy_expiration_date,
      row?.expiry_date,
      row?.expiration,
      row?.expirationDate,
      row?.policyExpirationDate,
      row?.["Expiration Date"],
      row?.["Policy Expiration Date"]
    );

    if (rowDate) return rowDate;
  }

  return "";
}

function lossqDaysUntilDate(value: any): number | null {
  const parsed = lossqParseDateForAge(value);
  if (!parsed) return null;

  const today = new Date();
  const todayUtc = Date.UTC(today.getFullYear(), today.getMonth(), today.getDate());
  const targetUtc = Date.UTC(parsed.getFullYear(), parsed.getMonth(), parsed.getDate());

  return Math.floor((targetUtc - todayUtc) / 86400000);
}

// LOSSQ_POLICY_EXPIRATION_ALERT_PRIORITY_V1
// LOSSQ_ALERT_RETURN_SHAPE_FIX_V1
function lossqEvaluationAlert(profileLike: any, policyRows: any[] = []) {
  const expirationRaw = lossqBestPolicyExpirationDateRaw(profileLike, policyRows);
  const daysUntilExpiration = lossqDaysUntilDate(expirationRaw);

  // LOSSQ_MISSING_POLICY_DATES_ALERT_V1
  // Policy lifecycle must be known before a loss run can be considered current.
  if (!expirationRaw || daysUntilExpiration === null) {
    return {
      status: "Policy Dates Missing",
      label: "Policy Dates Missing",
      tone: "red",
      message: "Policy effective/expiration dates could not be verified. Request a complete loss run with policy period before submitting to carriers.",
      detail: "Policy effective/expiration dates could not be verified. Request a complete loss run with policy period before submitting to carriers.",
    };
  }

  // Policy lifecycle comes first. A current valuation date does not make an expired policy current.
  if (daysUntilExpiration !== null && daysUntilExpiration < 0) {
    const expiredDays = Math.abs(daysUntilExpiration);

    return {
      status: "Policy Expired / Renewal Overdue",
      label: "Policy Expired / Renewal Overdue",
      tone: "red",
      message: `Policy expired ${expiredDays} day(s) ago. Request updated renewal loss runs before submitting to carriers.`,
      detail: `Policy expired ${expiredDays} day(s) ago. Request updated renewal loss runs before submitting to carriers.`,
    };
  }

  if (daysUntilExpiration !== null && daysUntilExpiration <= 30) {
    return {
      status: "Renewal Urgent",
      label: "Renewal Urgent",
      tone: "orange",
      message: `Policy expires in ${daysUntilExpiration} day(s). Request updated loss runs immediately before marketing.`,
      detail: `Policy expires in ${daysUntilExpiration} day(s). Request updated loss runs immediately before marketing.`,
    };
  }

  if (daysUntilExpiration !== null && daysUntilExpiration <= 90) {
    return {
      status: "Renewal Window",
      label: "Renewal Window",
      tone: "orange",
      message: `Policy expires in ${daysUntilExpiration} day(s). Updated loss runs should be requested for renewal marketing.`,
      detail: `Policy expires in ${daysUntilExpiration} day(s). Updated loss runs should be requested for renewal marketing.`,
    };
  }

  const raw = lossqEvaluationDateRaw(profileLike, policyRows);
  const ageDays = lossqEvaluationDateAgeDays(profileLike, policyRows);

  if (!raw || ageDays === null) {
    return {
      status: "Evaluation Date Missing",
      label: "Evaluation Date Missing",
      tone: "red",
      message: "Loss run valuation/evaluation date is missing. Request updated loss runs before submitting to carriers.",
      detail: "Loss run valuation/evaluation date is missing. Request updated loss runs before submitting to carriers.",
    };
  }

  if (ageDays <= 30) {
    return {
      status: "Current",
      label: "Current",
      tone: "green",
      message: `Loss run valuation date is ${ageDays} day(s) old.`,
      detail: `Loss run valuation date is ${ageDays} day(s) old.`,
    };
  }

  if (ageDays <= 60) {
    return {
      status: "Needs Refresh Soon",
      label: "Needs Refresh Soon",
      tone: "yellow",
      message: `Loss run valuation date is ${ageDays} day(s) old. Consider requesting an updated loss run before marketing.`,
      detail: `Loss run valuation date is ${ageDays} day(s) old. Consider requesting an updated loss run before marketing.`,
    };
  }

  if (ageDays <= 90) {
    return {
      status: "Refresh Recommended",
      label: "Refresh Recommended",
      tone: "orange",
      message: `Loss run valuation date is ${ageDays} day(s) old. Request an updated loss run before marketing.`,
      detail: `Loss run valuation date is ${ageDays} day(s) old. Request an updated loss run before marketing.`,
    };
  }

  return {
    status: "Outdated Loss Run",
    label: "Outdated Loss Run",
    tone: "red",
    message: `Loss run valuation date is ${ageDays} day(s) old. Request an updated loss run before submitting to carriers.`,
    detail: `Loss run valuation date is ${ageDays} day(s) old. Request an updated loss run before submitting to carriers.`,
  };
}


function EvaluationDateAlertBadge({ profileLike, policyRows }: { profileLike: any; policyRows: any[] }) {
  const alert = lossqEvaluationAlert(profileLike, policyRows);

  const toneClass =
    alert.tone === "green"
      ? "border-emerald-400/30 bg-emerald-500/10 text-emerald-200"
      : alert.tone === "yellow"
      ? "border-yellow-400/30 bg-yellow-500/10 text-yellow-100"
      : alert.tone === "orange"
      ? "border-orange-400/30 bg-orange-500/10 text-orange-100"
      : "border-red-400/30 bg-red-500/10 text-red-100";

  return (
    <div className={`mt-5 rounded-2xl border px-4 py-3 ${toneClass}`}>
      <div className="flex flex-col gap-1 md:flex-row md:items-center md:justify-between">
        <p className="text-sm font-bold">{alert.label}</p>
        <p className="text-xs opacity-90">{alert.detail}</p>
      </div>
    </div>
  );
}






// LOSSQ_SAFE_CARRIER_DISPLAY_V1
function lossqBadCarrierDisplayValue(value: any): boolean {
  const clean = lossqCleanText(value).toLowerCase();

  if (!clean) return true;

  const badValues = new Set([
    "effective",
    "effective date",
    "expiration",
    "expiration date",
    "expiry",
    "expiry date",
    "policy",
    "policy number",
    "carrier",
    "writing carrier",
    "insured",
    "named insured",
    "producer",
    "agency",
    "not set",
    "none",
    "null",
    "-",
  ]);

  if (badValues.has(clean)) return true;

  if (/^\d{1,2}[/-]\d{1,2}[/-]\d{2,4}$/.test(clean)) return true;
  if (/^\d{4}[/-]\d{1,2}[/-]\d{1,2}$/.test(clean)) return true;

  return false;
}

function lossqSafeCarrierDisplay(profileLike: any): string {
  const values = [
    profileLike?.carrier_name,
    profileLike?.writing_carrier,
    profileLike?.carrier,
    profileLike?.insurance_carrier,
    profileLike?.underwriting_carrier,
    profileLike?.["Carrier"],
    profileLike?.["Writing Carrier"],
  ];

  for (const value of values) {
    if (!lossqBadCarrierDisplayValue(value)) {
      return lossqCleanText(value);
    }
  }

  return "-";
}

function lossqSafeWritingCarrierDisplay(profileLike: any): string {
  const values = [
    profileLike?.writing_carrier,
    profileLike?.carrier_name,
    profileLike?.carrier,
    profileLike?.insurance_carrier,
    profileLike?.underwriting_carrier,
    profileLike?.["Writing Carrier"],
    profileLike?.["Carrier"],
  ];

  for (const value of values) {
    if (!lossqBadCarrierDisplayValue(value)) {
      return lossqCleanText(value);
    }
  }

  return "-";
}


// LOSSQ_PRODUCING_AGENCY_DISPLAY_HELPER_V1
// LOSSQ_PRODUCING_AGENCY_DISPLAY_UI_V1
function lossqProducingAgencyFromObject(obj: any): string {
  return lossqFirstValue(
    obj?.agency_name,
    obj?.producing_agency,
    obj?.producer,
    obj?.agency,
    obj?.agencyName,
    obj?.broker,
    obj?.brokerage,
    obj?.["Producing Agency"],
    obj?.["Producer"],
    obj?.["Agency Name"]
  ) || "Agency Not Set";
}


// LOSSQ_FRONTEND_DATE_LOCKDOWN_V1
// LOSSQ_FRONTEND_TARGETED_DATE_DISPLAY_V1
// LOSSQ_EXACT_ACCOUNT_POLICY_DATE_UI_V1
// LOSSQ_ACCOUNT_SNAPSHOT_EVALUATION_DATE_V1
// LOSSQ_POLICY_SCHEDULE_LINE_HELPER_UI_V1
function lossqFirstValue(...values: unknown[]): string {
  for (const value of values) {
    const cleaned = lossqCleanText(value);
    if (
      cleaned &&
      cleaned !== "-" &&
      cleaned.toLowerCase() !== "not set" &&
      cleaned.toLowerCase() !== "none" &&
      cleaned.toLowerCase() !== "null" &&
      cleaned.toLowerCase() !== "undefined"
    ) {
      return cleaned;
    }
  }
  return "";
}

function lossqEffectiveDateFromObject(obj: any): string {
  return lossqFormatDateSafe(
    obj?.effective_date,
    obj?.effectiveDate,
    obj?.effective,
    obj?.policy_effective_date,
    obj?.policyEffectiveDate,
    obj?.policy_effective,
    obj?.start_date,
    obj?.startDate
  );
}

function lossqExpirationDateFromObject(obj: any): string {
  return lossqFormatDateSafe(
    obj?.expiration_date,
    obj?.expirationDate,
    obj?.expiration,
    obj?.expiry_date,
    obj?.expiryDate,
    obj?.policy_expiration_date,
    obj?.policyExpirationDate,
    obj?.policy_expiration,
    obj?.end_date,
    obj?.endDate
  );
}

function lossqDateText(value: unknown): string {
  const formatted = lossqFormatDateSafe(value);
  return formatted || "Not set";
}

function lossqPolicyNumberFromObject(obj: any): string {
  return lossqFirstValue(
    obj?.policy_number,
    obj?.policyNumber,
    obj?.policy_no,
    obj?.policy,
    obj?.number
  ) || "Policy Not Set";
}

function lossqLineOfBusinessFromObject(obj: any): string {
  return lossqFirstValue(
    obj?.line_of_business,
    obj?.lineOfBusiness,
    obj?.policy_type,
    obj?.policyType,
    obj?.coverage,
    obj?.lob
  ) || "Line Not Set";
}




// LOSSQ_BETA_DASHBOARD_LABEL_V1
function lossqFormatBetaDate(value: any): string {
  if (!value) return "";

  try {
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return "";
    return date.toLocaleDateString(undefined, {
      month: "short",
      day: "numeric",
      year: "numeric",
    });
  } catch {
    return "";
  }
}

function lossqIsBetaPlan(status: any): boolean {
  const plan = String(status?.plan || status?.organization?.plan || "").trim().toLowerCase();
  return plan === "beta" || plan === "beta_access" || plan === "early_access";
}

function lossqBetaAccessLabel(status: any): string {
  if (!lossqIsBetaPlan(status)) return "";

  const uploadLimit =
    status?.upload_limit ??
    status?.organization?.upload_limit ??
    status?.limits?.upload_limit ??
    "";

  const expiresRaw =
    status?.current_period_end ??
    status?.organization?.current_period_end ??
    status?.subscription?.current_period_end ??
    "";

  const expires = lossqFormatBetaDate(expiresRaw);

  const pieces = ["Beta Access"];

  if (uploadLimit !== "" && uploadLimit !== null && uploadLimit !== undefined) {
    pieces.push(`${uploadLimit} uploads`);
  }

  if (expires) {
    pieces.push(`Expires ${expires}`);
  }

  return pieces.join(" • ");
}


export default function DashboardPage() {

  useEffect(() => {
    clearLossQDashboardTenantCache();
  }, []);

  const router = useRouter();

  // LOSSQ_BETA_FEEDBACK_BUTTON_V2
  const openBetaFeedbackEmail = () => {
    const subject = encodeURIComponent("LossQ Beta Feedback / Issue Report");

    const body = encodeURIComponent(
      [
        "LossQ Beta Feedback / Issue Report",
        "",
        "What happened?",
        "",
        "",
        "What were you trying to do?",
        "",
        "",
        "Page URL:",
        typeof window !== "undefined" ? window.location.href : "Dashboard",
        "",
        "Date/Time:",
        new Date().toLocaleString(),
        "",
        "Browser:",
        typeof navigator !== "undefined" ? navigator.userAgent : "Unknown",
        "",
        "Screenshots attached: Yes / No",
      ].join("\n")
    );

    window.location.href = `mailto:support@lossq.com?subject=${subject}&body=${body}`;
  };



  const [activeTool, setActiveTool] = useState<ToolKey>("overview");





// LOSSQ_CLAIM_ANALYSIS_SORTABLE_TABLE_V1
  const [claimAnalysisSort, setClaimAnalysisSort] = useState<{
    key: string;
    direction: "asc" | "desc";
  }>({
    key: "total",
    direction: "desc",
  });

useEffect(() => {
    if (typeof window === "undefined") return;

    const toolParam = new URLSearchParams(window.location.search).get("tool");
    const allowedTools: ToolKey[] = [
      "overview",
      "profiles",
      "upload",
      "exposure-inputs",
      "renewal-risk",
      "decision",
      "carrier-appetite",
      "submission-readiness",
      "carrier-match",
      "premium-forecast",
      "submission-builder",
      "summary",
      "memo",
      "charts",
      "claims",
    ];

    if (toolParam && allowedTools.includes(toolParam as ToolKey)) {
      setActiveTool(toolParam as ToolKey);
    }
  }, []);

  const [claims, setClaims] = useState<any[]>([]);
  const [isUploading, setIsUploading] = useState(false);
  const activeProfileRef = useRef<any>({});
  const dashboardLoadingRef = useRef(false);
  const loadVersionRef = useRef(0);
  const [summary, setSummary] = useState<any>({});
  const [decision, setDecision] = useState<any>({});
  const [carrierAppetite, setCarrierAppetite] = useState<any>({});
  const [submissionReadiness, setSubmissionReadiness] = useState<any>({});
  const [carrierMatch, setCarrierMatch] = useState<any>({});
  const [premiumForecast, setPremiumForecast] = useState<any>({});
  const [submissionBuilder, setSubmissionBuilder] = useState<any>({});
  const [timeline, setTimeline] = useState<any>({});
  // LOSSQ_TRUE_LAZY_LOADING_V1
  const [lazyLoadedTools, setLazyLoadedTools] = useState<Record<string, boolean>>({});
  const [lazyToolLoading, setLazyToolLoading] = useState<Record<string, boolean>>({});
  const [profile, setProfile] = useState<any>({});
  const [profiles, setProfiles] = useState<any[]>([]);
  // LOSSQ_BLANK_WORKSPACE_MODE_V1
  const [blankWorkspaceMode, setBlankWorkspaceMode] = useState(false);
function getAccountDisplayName(item: any) {
  return (
    item?.business_name ||
    item?.insured ||
    item?.named_insured ||
    item?.account_name ||
    item?.customer_name ||
    item?.company_name ||
    item?.name ||
    ""
  );
}

function normalizeProfileName(item: any) {
  const accountName = getAccountDisplayName(item);

  return {
    ...item,
    business_name: accountName || item?.business_name || "",
    insured: item?.insured || accountName || "",
  };
}
  const [files, setFiles] = useState<FileList | null>(null);


  const [message, setMessage] = useState("");
  const [billingStatus, setBillingStatus] = useState<any>({});
  const betaAccessLabel = lossqBetaAccessLabel(billingStatus);
  const [billingLoaded, setBillingLoaded] = useState(false);
  const [showNewUserWelcome, setShowNewUserWelcome] = useState(false);
  const [newUserWelcomeName, setNewUserWelcomeName] = useState("");
  const [authReady, setAuthReady] = useState(false);
  const [dashboardLoading, setDashboardLoading] = useState(true);
  const [dashboardError, setDashboardError] = useState("");

  const [copilotOpen, setCopilotOpen] = useState(false);
  const [copilotQuestion, setCopilotQuestion] = useState("");
  const [copilotAnswer, setCopilotAnswer] = useState("");
  const [copilotLoading, setCopilotLoading] = useState(false);
  const [selectedClaimDetail, setSelectedClaimDetail] = useState<any | null>(null);

  useEffect(() => {
    if (typeof window === "undefined") return;

    const toolParam = new URLSearchParams(window.location.search).get("tool");

    if (toolParam !== "claims") return;

    const cachedClaim = getCachedSelectedClaim();

    if (cachedClaim) {
      setSelectedClaimDetail(cachedClaim);
    }
  }, []);


  const [renewalMemo, setRenewalMemo] = useState("");
  const [memoLoading, setMemoLoading] = useState(false);

  useEffect(() => {
    async function validateSession() {
      const token = sessionStorage.getItem("lossq_tab_token") || localStorage.getItem("lossq_token");
      const loginTime = localStorage.getItem("lossq_login_time");

      if (!token) {
        router.replace("/login?fresh=1");
        return;
      }

      if (!loginTime) {
        localStorage.setItem("lossq_login_time", Date.now().toString());
      }

      if (loginTime) {
        const expired = Date.now() - Number(loginTime) > SESSION_TIMEOUT_MS;

        if (expired) {
          clearSession();
          router.replace("/login?expired=1");
          return;
        }
      }

      try {
        const validateRes = await fetch(`${API}/auth/validate`, {
          headers: {
            Authorization: `Bearer ${token}`,
          },
        });

        if (validateRes.status === 401 || validateRes.status === 403) {
          clearSession();
          router.replace("/login?expired=1");
          return;
        }
      } catch {
        setMessage("Session validation skipped. Backend validation unavailable.");
      }

      setAuthReady(true);
      await loadDashboard(getCachedSelectedPolicy());
    }

    validateSession();
  }, []);

  useEffect(() => {
    if (typeof window === "undefined") return;

    const validTools = [
      "overview",
      "profiles",
      "upload",
      "exposure-inputs",
      "submission-builder",
      "renewal-risk",
      "premium-forecast",
      "decision",
      "appetite",
      "readiness",
      "carrier-match",
      "summary",
      "memo",
      "charts",
      "claims",
    ];

    const toolFromUrl = new URLSearchParams(window.location.search).get("tool");
    const toolFromStorage = localStorage.getItem("lossq_active_tool");
    const nextTool = toolFromUrl || toolFromStorage;

    if (nextTool && validTools.includes(nextTool)) {
      setActiveTool(nextTool as ToolKey);
    }
  }, []);

  function clearSession() {
    localStorage.removeItem("lossq_token");
    sessionStorage.removeItem("lossq_tab_token");
    localStorage.removeItem("lossq_user");
    localStorage.removeItem("lossq_login_time");
    sessionStorage.removeItem("lossq_welcome");
  }

  function getToken() {
    if (typeof window === "undefined") return null;
    return sessionStorage.getItem("lossq_tab_token");
  }

  function authHeaders(): Record<string, string> {
    const token = getToken();
    return token ? { Authorization: `Bearer ${token}` } : {};
  }

  // LOSSQ_FRONTEND_SINGLE_SESSION_WATCHER_V1
  function handleSessionExpiredElsewhere() {
    clearSession();

    try {
      sessionStorage.setItem(
        "lossq_session_message",
        "Session expired because this account was signed in somewhere else."
      );
    } catch {
      // ignore storage errors
    }

    if (typeof window !== "undefined") {
      window.location.href = "/login?expired=shared";
      return;
    }

    router.replace("/login?expired=shared");
  }

  useEffect(() => {
    if (typeof window === "undefined") return;

    let stopped = false;

    // LOSSQ_FRONTEND_TAB_TOKEN_SNAPSHOT_V1
    // Keep the token that this dashboard tab opened with.
    // This prevents another tab/window in the same browser profile from overwriting
    // localStorage and making the old tab appear valid.
    const tabToken = sessionStorage.getItem("lossq_tab_token");

    async function checkActiveSession() {
      const token = tabToken;

      if (!token || stopped) return;

      try {
        const res = await fetch(`${API}/auth/me?session_check=${Date.now()}`, {
          method: "GET",
          headers: {
            Authorization: `Bearer ${token}`,
            "Cache-Control": "no-cache",
            Pragma: "no-cache",
          },
          cache: "no-store",
        });

        if (res.status === 401 || res.status === 403) {
          if (!stopped) {
            handleSessionExpiredElsewhere();
          }
        }
      } catch {
        // Do not log users out for temporary network issues.
      }
    }

    const intervalId = window.setInterval(checkActiveSession, 5000);

    const handleFocus = () => {
      checkActiveSession();
    };

    const handleVisibilityChange = () => {
      if (document.visibilityState === "visible") {
        checkActiveSession();
      }
    };

    // LOSSQ_FRONTEND_SINGLE_SESSION_CLICK_CHECK_V1
    const handleUserActivity = () => {
      checkActiveSession();
    };

    window.addEventListener("focus", handleFocus);
    window.addEventListener("click", handleUserActivity);
    window.addEventListener("touchstart", handleUserActivity);
    document.addEventListener("visibilitychange", handleVisibilityChange);

    checkActiveSession();

    return () => {
      stopped = true;
      window.clearInterval(intervalId);
      window.removeEventListener("focus", handleFocus);
      window.removeEventListener("click", handleUserActivity);
      window.removeEventListener("touchstart", handleUserActivity);
      document.removeEventListener("visibilitychange", handleVisibilityChange);
    };
  }, []);



  // LOSSQ_NAMED_WELCOME_BANNER_V1
  function getNewUserWelcomeName() {
    if (typeof window === "undefined") return "";

    const storedName =
      sessionStorage.getItem("lossq_welcome_name") ||
      localStorage.getItem("lossq_new_user_welcome_name") ||
      "";

    if (storedName.trim()) return storedName.trim();

    try {
      const rawUser = localStorage.getItem("lossq_user");
      const user = rawUser ? JSON.parse(rawUser) : null;
      const fullName = `${user?.first_name || ""} ${user?.last_name || ""}`.trim();
      return fullName || user?.name || user?.email || "";
    } catch {
      return "";
    }
  }


  // LOSSQ_NEW_USER_WELCOME_FINAL_V1
  useEffect(() => {
    if (typeof window === "undefined") return;

    const params = new URLSearchParams(window.location.search);
    const welcomeParam = params.get("welcome");
    const pendingWelcome =
      sessionStorage.getItem("lossq_welcome") ||
      localStorage.getItem("lossq_new_user_welcome");

    const seen = localStorage.getItem("lossq_new_user_welcome_seen");

    if (
      !seen &&
      (welcomeParam === "1" ||
        pendingWelcome === "1" ||
        pendingWelcome === "true" ||
        pendingWelcome === "new-user")
    ) {
      setNewUserWelcomeName(getNewUserWelcomeName());
      setShowNewUserWelcome(true);

      if (welcomeParam) {
        params.delete("welcome");
        const cleanUrl = `${window.location.pathname}${
          params.toString() ? `?${params.toString()}` : ""
        }`;
        window.history.replaceState({}, "", cleanUrl);
      }
    }
  }, []);

  function dismissNewUserWelcome() {
    if (typeof window !== "undefined") {
      localStorage.setItem("lossq_new_user_welcome_seen", Date.now().toString());
      localStorage.removeItem("lossq_new_user_welcome");
      localStorage.removeItem("lossq_new_user_welcome_name");
      sessionStorage.removeItem("lossq_welcome");
      sessionStorage.removeItem("lossq_welcome_name");
    }

    setShowNewUserWelcome(false);
  }


  // LOSSQ_PACKAGE_FUNCTION_LIMITS_DASHBOARD_V1
  useEffect(() => {
    if (!authReady) return;

    async function loadBillingStatusForLimits() {
      try {
        const res = await fetch(`${API}/billing/status`, {
          headers: authHeaders(),
        });

        const data = res.ok ? ((await safeJson(res)) || {}) : {};
        setBillingStatus(data);
      } catch {
        setBillingStatus({});
      } finally {
        setBillingLoaded(true);
      }
    }

    loadBillingStatusForLimits();
  }, [authReady]);

  function normalizeDashboardPlan(plan: any) {
    const clean = String(plan || "free").trim().toLowerCase();

    if (clean === "founder" || clean === "founding" || clean === "founding agency") {
      return "founding_agency";
    }

    if (clean === "pro") return "professional";
    if (clean === "enterprise") return "agency";
    if (clean === "beta" || clean === "beta_access" || clean === "early_access") return "beta";

    return LOSSQ_PLAN_FUNCTION_LIMITS[clean] ? clean : "free";
  }

  function getDashboardPlan() {
    return normalizeDashboardPlan(
      billingStatus?.plan ||
        billingStatus?.subscription_plan ||
        billingStatus?.plan_name ||
        "free"
    );
  }


  // LOSSQ_DASHBOARD_PAYMENT_GATE_V1
  const PAID_DASHBOARD_PLANS = new Set([

    "beta",
    "starter",
    "professional",
    "agency",
    "founding_agency",
  ]);

  const ACTIVE_DASHBOARD_BILLING_STATUSES = new Set([
    "active",
    "paid",
  ]);

  function normalizeDashboardBillingStatus(status: any) {
    const clean = String(status || "").trim().toLowerCase();
    return clean || "unpaid";
  }

  function getDashboardBillingStatus() {
    return normalizeDashboardBillingStatus(
      billingStatus?.subscription_status ||
        billingStatus?.status ||
        billingStatus?.billing_status ||
        billingStatus?.organization?.subscription_status
    );
  }

  function isDashboardBillingUnlocked() {
    if (!billingLoaded) return false;

    const plan = getDashboardPlan();
    const status = getDashboardBillingStatus();

    return PAID_DASHBOARD_PLANS.has(plan) && ACTIVE_DASHBOARD_BILLING_STATUSES.has(status);
  }

  function getDashboardPaymentLockMessage() {
    const plan = getDashboardPlan();
    const status = getDashboardBillingStatus();

    if (!PAID_DASHBOARD_PLANS.has(plan)) {
      return "A paid LossQ subscription or approved beta access is required before you can access the dashboard.";
    }

    return `Your ${plan} subscription is currently ${status}. Please update billing to continue using the dashboard.`;
  }

  // LOSSQ_MERGE_SERVER_AND_LOCAL_PLAN_FEATURES_V1
  function getDashboardPlanFeatures() {
    const serverFeatures = Array.isArray(billingStatus?.features)
      ? billingStatus.features.map((item: any) => String(item))
      : [];

    const localFeatures =
      LOSSQ_PLAN_FUNCTION_LIMITS[getDashboardPlan()] ||
      LOSSQ_PLAN_FUNCTION_LIMITS.free ||
      [];

    return Array.from(new Set([...localFeatures, ...serverFeatures]));
  }

  function canUseFeature(feature: string) {
    if (!billingLoaded) return true;

    const features = getDashboardPlanFeatures();
    return features.includes(feature);
  }

  function canUseTool(tool: ToolKey) {
    const feature = LOSSQ_TOOL_REQUIRED_FEATURE[String(tool)];
    if (!feature) return true;
    return canUseFeature(feature);
  }

  function getLockedFeatureMessage(tool: ToolKey) {
    const feature = LOSSQ_TOOL_REQUIRED_FEATURE[String(tool)] || String(tool);
    const label = LOSSQ_FEATURE_LABELS[feature] || feature;
    const plan = billingStatus?.plan_limits?.label || billingStatus?.label || getDashboardPlan();

    return `${label} is not included in the current ${plan} package. Upgrade the account package to unlock this function.`;
  }


  // LOSSQ_IDLE_TIMEOUT_60_MINUTES_V1
  useEffect(() => {
    if (typeof window === "undefined") return;

    const IDLE_LIMIT_MS = 60 * 60 * 1000;
    const ACTIVITY_KEY = "lossq_last_activity_at";
    const TIMEOUT_MESSAGE_KEY = "lossq_session_timeout_message";

    let timeoutId: number | null = null;
    let lastWrite = 0;

    function hasActiveToken() {
      return Boolean(sessionStorage.getItem("lossq_tab_token"));
    }

    function expireIdleSession() {
      if (!hasActiveToken()) return;

      sessionStorage.setItem(
        TIMEOUT_MESSAGE_KEY,
        "Your session timed out after 60 minutes of inactivity. Please log in again."
      );

      clearSession();
      router.replace("/login?timeout=1");
    }

    function scheduleIdleCheck() {
      if (timeoutId) window.clearTimeout(timeoutId);

      if (!hasActiveToken()) return;

      const lastActivity = Number(localStorage.getItem(ACTIVITY_KEY) || Date.now());
      const elapsed = Date.now() - lastActivity;
      const remaining = Math.max(IDLE_LIMIT_MS - elapsed, 0);

      timeoutId = window.setTimeout(() => {
        const latestActivity = Number(localStorage.getItem(ACTIVITY_KEY) || 0);

        if (Date.now() - latestActivity >= IDLE_LIMIT_MS) {
          expireIdleSession();
          return;
        }

        scheduleIdleCheck();
      }, remaining || 1000);
    }

    function markActivity() {
      if (!hasActiveToken()) return;

      const now = Date.now();

      // Avoid writing localStorage constantly during mousemove.
      if (now - lastWrite < 30000) return;

      lastWrite = now;
      localStorage.setItem(ACTIVITY_KEY, String(now));
      scheduleIdleCheck();
    }

    function handleStorage(event: StorageEvent) {
      if (event.key === ACTIVITY_KEY) {
        scheduleIdleCheck();
      }
    }

    if (!localStorage.getItem(ACTIVITY_KEY)) {
      localStorage.setItem(ACTIVITY_KEY, String(Date.now()));
    }

    const events = ["click", "keydown", "mousemove", "scroll", "touchstart"];

    events.forEach((eventName) => {
      window.addEventListener(eventName, markActivity, { passive: true });
    });

    window.addEventListener("storage", handleStorage);
    scheduleIdleCheck();

    return () => {
      if (timeoutId) window.clearTimeout(timeoutId);

      events.forEach((eventName) => {
        window.removeEventListener(eventName, markActivity);
      });

      window.removeEventListener("storage", handleStorage);
    };
  }, [router]);

  // LOSSQ_PERSIST_ACTIVE_TOOL_V1
  function changeActiveTool(tool: ToolKey) {
    if (!canUseTool(tool)) {
      setMessage(getLockedFeatureMessage(tool));
      setActiveTool("overview");
      return;
    }

    setActiveTool(tool);

    if (typeof window !== "undefined") {
      localStorage.setItem("lossq_active_tool", tool);
      const url = new URL(window.location.href);
      url.searchParams.set("tool", tool);
      window.history.replaceState({}, "", url.toString());
    }
  }

  function updateProfileList(incomingProfiles: AnyObject[]) {
    const cleanedIncoming = (incomingProfiles || [])
      .filter(Boolean)
      .map((item) => normalizeProfileName(item))
      .map((item) => {
        const safePolicyNumber = chooseSafePolicyNumber(
          item?.policy_number,
          item?.account_number,
          item?.customer_number
        );

        return {
          ...item,
          policy_number: safePolicyNumber || "",
          account_number: item?.account_number || item?.customer_number || "",
          customer_number: item?.customer_number || item?.account_number || "",
        };
      });

    setProfiles((prev) => {
      const merged = [
        ...cleanedIncoming,
        ...prev.map((item) => normalizeProfileName(item)),
      ];

      const seen = new Set<string>();

      const next = merged.filter((item) => {
        const safePolicy = chooseSafePolicyNumber(
          item?.account_number,
          item?.customer_number,
          item?.policy_number
        );

        const key =
          item?.id ||
          item?.account_number ||
          item?.customer_number ||
          safePolicy ||
          `${getAccountDisplayName(item)}-${item?.carrier_name || item?.writing_carrier || ""}`;

        if (!key) return false;

        const normalizedKey = String(key).trim().toUpperCase();

        if (seen.has(normalizedKey)) return false;

        seen.add(normalizedKey);
        return true;
      });

      setCachedProfiles(next);
      return next;
    });
  }


  async function loadProfileList() {
    try {
      const cachedProfiles = getCachedProfiles();

      if (Array.isArray(cachedProfiles) && cachedProfiles.length > 0) {
        const normalizedCached = cachedProfiles.map((item: AnyObject) =>
          normalizeProfileName(item)
        );
        setProfiles(normalizedCached);
      }

      const profilesRes = await fetch(`${API}/account-profile/all`, {
        headers: authHeaders(),
      });

      if (profilesRes.status === 401 || profilesRes.status === 403) {
        clearSession();
        router.replace("/login?expired=1");
        return;
      }

      if (!profilesRes.ok) {
        return;
      }

      const data = await safeJson(profilesRes);
      const serverProfiles = Array.isArray(data)
        ? data
        : Array.isArray(data?.profiles)
        ? data.profiles
        : [];

      updateProfileList(serverProfiles);
    } catch {
      // Keep dashboard usable if profile list fetch fails.
    }
  }

  function newBlankProfile() {
    resetActiveWorkspace("New blank account profile started.");
    setActiveTool("profiles");
  }

  function resetActiveWorkspace(messageText?: string) {
    // Blank workspace must not inherit any old file/profile/policy/claim context.
    setBlankWorkspaceMode(true);
    activeProfileRef.current = {};

    setProfile({
      business_name: "",
      carrier_name: "",
      writing_carrier: "",
      agency_name: "",
      account_number: "",
      customer_number: "",
      producer_number: "",
      policy_number: "",
      effective_date: "",
      expiration_date: "",
      evaluation_date: "",
      policies: [],
      validation: {},
      raw_text_preview: "",
    });

    setClaims(lossqFilterRealClaims([]));
    setSummary({});
    setDecision({});
    setCarrierAppetite({});
    setSubmissionReadiness({});
    setCarrierMatch({});
    setPremiumForecast({});
    setSubmissionBuilder({});
    setTimeline({});
    setLazyLoadedTools({});
    setLazyToolLoading({});
    setRenewalMemo("");
    setCopilotAnswer("");
    setSelectedClaimDetail(null);

    clearCachedSelectedPolicy();
    clearCachedSelectedClaim();
    clearCachedLastUploadReview();
    clearCachedCurrentUpload();

    if (messageText) {
      setMessage(messageText);
    }
  }

  async function loadDashboard(policyNumberOverride?: string, skipProfileList = false) {
    if (!getToken()) {
      router.replace("/login?fresh=1");
      return;
    }

    setDashboardLoading(true);
    const myVersion = ++loadVersionRef.current;
    setDashboardError("");

    const cachedPolicyNumber = getCachedSelectedPolicy();
    const requestedPolicyNumber = normalizePolicyNumber(policyNumberOverride || cachedPolicyNumber);

    try {
      if (!skipProfileList) await loadProfileList();

    // Pre-load ref from cache immediately so filteredVisibleClaims has correct policies on first render
    if (requestedPolicyNumber) {
      const earlyMatch = getCachedProfiles().find((p: any) =>
        normalizePolicyNumber(p?.policy_number) === requestedPolicyNumber ||
        (p?.policies || []).some((pol: any) => normalizePolicyNumber(pol?.policy_number) === requestedPolicyNumber)
      );
      if (earlyMatch && (earlyMatch.policies || []).length > 0) {
        activeProfileRef.current = earlyMatch;
      }
    }

      let activeProfile = profile;

      if (requestedPolicyNumber) {
        const selectedRes = await fetch(
          `${API}/account-profile/policy/${encodeURIComponent(requestedPolicyNumber)}`,
          { headers: authHeaders() }
        );

        if (selectedRes.status === 401 || selectedRes.status === 403) {
          clearSession();
          router.replace("/login?expired=1");
          return;
        }

        if (selectedRes.ok) {
          const fetchedProfile = (await safeJson(selectedRes)) || {};
          const cachedMatch = getCachedProfiles().find(
            (item) => normalizePolicyNumber(item?.policy_number) === requestedPolicyNumber
          );

          activeProfile = {
            ...(cachedMatch || {}),
            ...fetchedProfile,
            policies:
              ((fetchedProfile?.policies?.length || 0) >= (cachedMatch?.policies?.length || 0)
                ? fetchedProfile?.policies
                : cachedMatch?.policies) ||
              fetchedProfile?.policies ||
              cachedMatch?.policies ||
              profile?.policies ||
              [],
            validation:
              fetchedProfile?.validation ||
              cachedMatch?.validation ||
              profile?.validation ||
              {},
          };

          setBlankWorkspaceMode(false);
          activeProfileRef.current = activeProfile || {};
          setProfile(activeProfile || {});
          if (activeProfile?.policy_number) {
            updateProfileList([activeProfile]);
          }
        } else {
          const cachedMatch = getCachedProfiles().find(
            (item) => normalizePolicyNumber(item?.policy_number) === requestedPolicyNumber
          );

          if (cachedMatch) {
  activeProfile = normalizeProfileName(cachedMatch);
  setBlankWorkspaceMode(false);
  setProfile(activeProfile);
}
        }
      } else {
        const profileRes = await fetch(`${API}/account-profile/`, {
          headers: authHeaders(),
        });

        if (profileRes.status === 401 || profileRes.status === 403) {
          clearSession();
          router.replace("/login?expired=1");
          return;
        }

        if (profileRes.ok) {
          const fetchedProfile = (await safeJson(profileRes)) || {};
          const cachedMatch = getCachedProfiles().find(
            (item) => item?.policy_number === fetchedProfile?.policy_number
          );

          activeProfile = normalizeProfileName({
  ...(cachedMatch || {}),
  ...fetchedProfile,

  business_name:
    fetchedProfile?.business_name ||
    fetchedProfile?.insured ||
    fetchedProfile?.named_insured ||
    fetchedProfile?.account_name ||
    cachedMatch?.business_name ||
    cachedMatch?.insured ||
    cachedMatch?.named_insured ||
    cachedMatch?.account_name ||
    "",

  insured:
    fetchedProfile?.insured ||
    fetchedProfile?.business_name ||
    fetchedProfile?.named_insured ||
    fetchedProfile?.account_name ||
    cachedMatch?.insured ||
    cachedMatch?.business_name ||
    cachedMatch?.named_insured ||
    cachedMatch?.account_name ||
    "",

  policies:
    fetchedProfile?.policies ||
    cachedMatch?.policies ||
    profile?.policies ||
    [],
  validation:
    fetchedProfile?.validation ||
    cachedMatch?.validation ||
    profile?.validation ||
    {},
});

          setBlankWorkspaceMode(false);
          setProfile(activeProfile || {});
          activeProfileRef.current = activeProfile || {};
if (activeProfile?.policy_number) {
  updateProfileList([activeProfile]);
}

        } else {
          const cachedProfiles = getCachedProfiles();
          if (cachedProfiles.length > 0 && !activeProfile?.policy_number) {
            activeProfile = cachedProfiles[0];
            setBlankWorkspaceMode(false);
            setProfile(cachedProfiles[0]);
          }
        }
      }

      const policyNumber =
        requestedPolicyNumber ||
        activeProfile?.policy_number ||
        profile?.policy_number ||
        "";

      const hasPolicy = policyNumber && policyNumber !== "Policy Not Set";

      if (hasPolicy) {
        setCachedSelectedPolicy(policyNumber);
      }

// LOSSQ_FIX_MISSING_HASPOLICY_IF_V1
      if (hasPolicy) {
      /*
        Always fetch all organization claims here.
        The dashboard filters locally through visibleClaims so account policies
        like SA-ACCT-580219 can count child-policy claims such as SA-AUTO,
        SA-GL, SA-CARGO, and SA-WC correctly.
      */
      // LOSSQ_ACCOUNT_AWARE_CLAIMS_RELOAD_V1
      // Include account/customer keys in the server request.
      // Without this, upload can show 19 claims from cache, but refresh/login only reloads child policy claims.
      // LOSSQ_SELECTED_PROFILE_ONLY_CLAIM_RELOAD_V1
      // Use the active loaded profile only. Do not merge old profile/ref/cached policy lists.
      const selectedClaimsProfile: any = activeProfile || {};
      const claimReloadKeys: string[] = [
        policyNumber,
        requestedPolicyNumber,
        selectedClaimsProfile?.policy_number,
        selectedClaimsProfile?.account_number,
        selectedClaimsProfile?.customer_number,
        ...(selectedClaimsProfile?.policies || []).map((p: any) => p?.policy_number),
      ]
        .map((item: any) => normalizePolicyNumber(item))
        .filter((item: string) => Boolean(item));

      const uniqueClaimReloadKeys: string[] = Array.from(new Set<string>(claimReloadKeys));
      const policySet = new Set<string>(uniqueClaimReloadKeys);

      // LOSSQ_RESTORE_SELECTED_PROFILE_SERVER_CLAIMS_FETCH_V1
      const claimsUrl =
        uniqueClaimReloadKeys.length > 0
          ? `${API}/claims/?policy_numbers=${encodeURIComponent(uniqueClaimReloadKeys.join(","))}`
          : `${API}/claims/`;

      const claimsResponse = await fetch(claimsUrl, {
        headers: {
          Authorization: `Bearer ${getToken() || ""}`,
        },
      });

      const serverClaims: any[] = claimsResponse.ok ? await claimsResponse.json() : [];

      // LOSSQ_TRUST_BACKEND_CLAIMS_RESPONSE_V1
      // The backend /claims endpoint already filters by the selected account/policy keys.
      // Do not re-filter locally with claimMatchesPolicySet because it can drop valid child-policy
      // rows such as FPS-CARGO-2025-8804 after parser cleanup.
      const serverMatches = serverClaims;

        // LOSSQ_BACKEND_ONLY_LOAD_DASHBOARD_CLAIMS_V1
        // Backend /claims is the only source of truth for Claims Analysis rows.
        // Do not fall back to current upload cache or last upload cache because those can carry stale policy/line values.
        if (myVersion === loadVersionRef.current) {
          const cleanedServerClaims = lossqFilterRealClaims(serverMatches);
          // LOSSQ_FRONTEND_CLAIMS_STATE_DEBUG_V1
          console.log("LOSSQ_FRONTEND_CLAIMS_STATE_DEBUG", {
            claimsUrl,
            serverClaimsCount: Array.isArray(serverClaims) ? serverClaims.length : 0,
            cleanedServerClaimsCount: Array.isArray(cleanedServerClaims) ? cleanedServerClaims.length : 0,
            sample: Array.isArray(cleanedServerClaims) ? cleanedServerClaims.slice(0, 3) : [],
          });
          setClaims(cleanedServerClaims);
        }
      } else {
        if (myVersion === loadVersionRef.current) {
          setClaims(lossqFilterRealClaims([]));
        }
      }

      // LOSSQ_TRUE_LAZY_LOADING_V1
      // Heavy underwriting/renewal/submission/timeline tools are now lazy-loaded
      // only when their tab is opened. Initial dashboard load stays limited to
      // profile + claims + overview.

    } catch {
      console.log("CATCH BLOCK HIT:", arguments[0] || "unknown error");
      setDashboardError("Dashboard could not load. Confirm backend is running.");
      if (myVersion === loadVersionRef.current) setClaims(lossqFilterRealClaims([]));
      setSummary({});
      setDecision({});
      setCarrierAppetite({});
      setSubmissionReadiness({});
      setCarrierMatch({});
      setTimeline({});
    } finally {
      setDashboardLoading(false);
    }
  }

  async function loadLazyToolData(toolKey: ToolKey) {
    if (!canUseTool(toolKey)) {
      setMessage(getLockedFeatureMessage(toolKey));
      console.log("Lazy tool blocked by package gate:", toolKey);
      return;
    }

    const heavyTools: ToolKey[] = [
      "summary",
      "memo",
      "renewal-risk",
      "decision",
      "carrier-appetite",
      "submission-readiness",
      "carrier-match",
      "premium-forecast",
      "submission-builder",
      "charts",
    ];

    if (!heavyTools.includes(toolKey)) return;
    if (lazyLoadedTools[toolKey] || lazyToolLoading[toolKey]) return;

    const selectedPolicy =
      normalizePolicyNumber(
        getCachedSelectedPolicy() ||
          profile?.policy_number ||
          activeProfileRef.current?.policy_number ||
          safeDisplayProfile?.account_number ||
          activeProfileRef.current?.account_number ||
          ""
      );

    const hasPolicy = selectedPolicy && selectedPolicy !== "POLICY NOT SET";

    const withPolicy = (base: string) =>
      hasPolicy ? `${base}?policy_number=${encodeURIComponent(selectedPolicy)}` : base;

    let url = "";

    if (toolKey === "summary" || toolKey === "memo" || toolKey === "renewal-risk") {
      url = withPolicy(`${API}/summary/underwriting`);
    }

    if (toolKey === "decision") {
      url = withPolicy(`${API}/renewal/decision`);
    }

    if (toolKey === "carrier-appetite") {
      url = withPolicy(`${API}/renewal/carrier-appetite`);
    }

    if (toolKey === "submission-readiness") {
      url = withPolicy(`${API}/renewal/submission-readiness`);
    }

    if (toolKey === "carrier-match") {
      url = withPolicy(`${API}/renewal/carrier-match`);
    }

    if (toolKey === "premium-forecast") {
      url = withPolicy(`${API}/renewal/premium-forecast`);
    }

    if (toolKey === "submission-builder") {
      url = hasPolicy
        ? `${API}/submission-builder/?policy_number=${encodeURIComponent(selectedPolicy)}`
        : `${API}/submission-builder/`;
    }

    if (toolKey === "charts") {
      url = withPolicy(`${API}/timeline/analytics`);
    }

    if (!url) return;

    setLazyToolLoading((prev) => ({ ...prev, [toolKey]: true }));

    try {
      const res = await fetch(url, { headers: authHeaders() });

      if (res.status === 401 || res.status === 403) {
        clearSession();
        router.replace("/login?expired=1");
        return;
      }

      const data = res.ok ? ((await safeJson(res)) || {}) : {};

      if (toolKey === "summary" || toolKey === "memo" || toolKey === "renewal-risk") {
        setSummary(data);
      }

      if (toolKey === "decision") {
        setDecision(data);
      }

      if (toolKey === "carrier-appetite") {
        setCarrierAppetite(data);
      }

      if (toolKey === "submission-readiness") {
        setSubmissionReadiness(data);
      }

      if (toolKey === "carrier-match") {
        setCarrierMatch(data);
      }

      if (toolKey === "premium-forecast") {
        setPremiumForecast(data);
      }

      if (toolKey === "submission-builder") {
        setSubmissionBuilder(data);
      }

      if (toolKey === "charts") {
        setTimeline(data);
      }

      setLazyLoadedTools((prev) => ({ ...prev, [toolKey]: true }));
    } catch {
      // Keep the dashboard usable even if a lazy tool fails.
    } finally {
      setLazyToolLoading((prev) => ({ ...prev, [toolKey]: false }));
    }
  }

  useEffect(() => {
    loadLazyToolData(activeTool);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeTool, profile?.policy_number, profile?.account_number]);

  // LOSSQ_CLEAR_STALE_EXPOSURE_AUTOFILL_MESSAGE_V1
  useEffect(() => {
    if (activeTool !== "exposure-inputs") return;

    setMessage((current) => {
      const value = String(current || "");
      if (
        value.includes("No exposure values were found on this profile yet") ||
        value.includes("Exposure values were found, but existing manual values were preserved")
      ) {
        return "";
      }
      return current;
    });
  }, [activeTool, profile?.policy_number, profile?.account_number]);

  async function selectAccount(policyNumber: string) {
    resetProfileAnalyticsState({
      setSummary,
      setDecision,
      setCarrierAppetite,
      setSubmissionReadiness,
      setCarrierMatch,
      setPremiumForecast,
      setSubmissionBuilder,
      setTimeline,
setLazyLoadedTools,
      setLazyToolLoading,
    });

    if (!policyNumber) return;

    const normalizedPolicy = normalizePolicyNumber(policyNumber);

    setCachedSelectedPolicy(normalizedPolicy);

    // Clear stale dashboard state immediately so the previous profile's claims
    // cannot remain visible while the new account is loading.
    setClaims(lossqFilterRealClaims([]));
    setSelectedClaimDetail(null);
    clearCachedSelectedClaim();
    clearCachedCurrentUpload();

    setMessage(`Loading policy ${normalizedPolicy}...`);
    setCopilotAnswer("");
    setRenewalMemo("");
    setSummary({});
    setDecision({});
    setCarrierAppetite({});
    setSubmissionReadiness({});
    setCarrierMatch({});
    setPremiumForecast({});
    setSubmissionBuilder({});
    setTimeline({});
    setLazyLoadedTools({});
    setLazyToolLoading({});

    // Pre-load the full profile from cache so policySet includes all sibling policies.
    const cachedMatch = getCachedProfiles().find(
      (p: any) =>
        normalizePolicyNumber(p?.policy_number) === normalizedPolicy ||
        normalizePolicyNumber(p?.account_number) === normalizedPolicy ||
        normalizePolicyNumber(p?.customer_number) === normalizedPolicy ||
        (p?.policies || []).some(
          (pol: any) => normalizePolicyNumber(pol?.policy_number) === normalizedPolicy
        )
    );

    if (cachedMatch) {
      activeProfileRef.current = cachedMatch;
      setProfile(cachedMatch);
    } else {
      activeProfileRef.current = {};
    }

    await loadDashboard(normalizedPolicy, true);
    setMessage(`Loaded policy ${normalizedPolicy}.`);
  }
  async function deleteProfile(profileToDelete: any) {
    const profileId = profileToDelete?.id;
    const policyNumber =
    profileToDelete?.policy_number ||
    profileToDelete?.account_number ||
    profileToDelete?.customer_number ||
    "";

  const profileLabel =
    profileToDelete?.business_name ||
    profileToDelete?.insured ||
    profileToDelete?.named_insured ||
    profileToDelete?.account_name ||
    policyNumber ||
    "this profile";

  if (!profileId && !policyNumber) {
    setMessage("No saved profile selected to delete.");
    return;
  }

  const confirmed = confirm(`Delete ${profileLabel}?`);
  if (!confirmed) return;

  const removeProfileLocally = () => {
    setProfiles((prev) => {
      const next = prev.filter((p) => {
        if (profileId && p?.id === profileId) return false;

        const existingPolicy =
          p?.policy_number ||
          p?.account_number ||
          p?.customer_number ||
          "";

        if (!profileId && policyNumber && existingPolicy === policyNumber) return false;
        return true;
      });

      setCachedProfiles(next);
      return next;
    });

    resetActiveWorkspace();
    setActiveTool("profiles");
  };

  // Do not clear local/profile state until backend confirms delete.
  // Clearing browser traces first can remove the tab auth token and cause logout.
  setMessage(`Deleting ${profileLabel}...`);

  try {
    const deleteUrl = profileId
      ? `${API}/account-profile/id/${encodeURIComponent(String(profileId))}?delete_claims=true`
      : `${API}/account-profile/?policy_number=${encodeURIComponent(policyNumber)}&delete_claims=true`;

    const res = await fetch(deleteUrl, {
      method: "DELETE",
      headers: authHeaders(),
    });

    if (res.status === 401 || res.status === 403) {
      clearSession();
      router.replace("/login?expired=1");
      return;
    }

    const data = await safeJson(res);

    if (!res.ok || data?.deleted === false) {
      setMessage(
        `Could not delete ${profileLabel}. Backend response: ${
          data?.message || res.status
        }`
      );
      return;
    }

    clearDeletedProfileBrowserTraces(profileToDelete);
    clearCachedCurrentUpload();
    clearCachedSelectedClaim();
    clearCachedLastUploadReview();
    removeProfileLocally();
    resetActiveWorkspace();
    setActiveTool("profiles");
    await loadProfileList();
    setMessage(`Deleted ${profileLabel}. All related local upload traces were cleared.`);
  } catch {
    setMessage(`Could not delete ${profileLabel}. Backend delete unavailable.`);
  }
}


async function saveProfile() {
  const payload = {
    id: profile?.id || null,
    business_name: profile?.business_name || "",
    carrier_name: profile?.carrier_name || "",
    writing_carrier: profile?.writing_carrier || profile?.carrier_name || "",
    agency_name: profile?.agency_name || "",
    account_number: lossqCleanAccountNumber(profile?.account_number),
    customer_number: lossqCleanAccountNumber(profile?.customer_number || profile?.account_number),
    producer_number: profile?.producer_number || "",
    policy_number: profile?.policy_number || "",
    effective_date: profile?.effective_date || "",
    expiration_date: profile?.expiration_date || "",
    evaluation_date: getBestEvaluationDate(profile) || "",
    policies: Array.isArray(profile?.policies) ? profile.policies : [],
    validation: profile?.validation || {},
    raw_text_preview: profile?.raw_text_preview || "",
  };

  const saveKey =
    payload.account_number ||
    payload.customer_number ||
    payload.policy_number;

  if (!saveKey) {
    setMessage("Account number or policy number is required before saving.");
    return;
  }

  try {
    setMessage("Saving account profile...");

    const res = await fetch(`${API}/account-profile/`, {
      method: "PUT",
      headers: {
        "Content-Type": "application/json",
        ...authHeaders(),
      },
      body: JSON.stringify(payload),
    });

    if (res.status === 401 || res.status === 403) {
      clearSession();
      router.replace("/login?expired=1");
      return;
    }

    if (!res.ok) {
      updateProfileList([payload]);
      setMessage("Saved profile locally. Backend save failed.");
      return;
    }

    const savedData = await safeJson(res);
    const savedProfile = savedData?.id ? savedData : payload;

    setProfile(savedProfile);
    updateProfileList([savedProfile]);

    const selectedPolicy =
      savedProfile?.policy_number ||
      savedProfile?.account_number ||
      savedProfile?.customer_number ||
      "";

    if (selectedPolicy) {
      setCachedSelectedPolicy(selectedPolicy);
      await loadDashboard(selectedPolicy);
    }

    setMessage("Account profile saved.");
  } catch {
    updateProfileList([payload]);
    setMessage("Saved profile locally. Backend save unavailable.");
  }
}

  async function lookupPolicy() {
    if (!profile.policy_number) {
      setMessage("Enter a policy number first.");
      return;
    }

    try {
      const res = await fetch(
        `${API}/account-profile/policy/${encodeURIComponent(profile.policy_number)}`,
        { headers: authHeaders() }
      );

      if (res.status === 401 || res.status === 403) {
        clearSession();
        router.replace("/login?expired=1");
        return;
      }

      if (!res.ok) {
        const cachedMatch = getCachedProfiles().find(
          (item) => item?.policy_number === profile.policy_number
        );

        if (cachedMatch) {
          setProfile(cachedMatch);
          setCopilotAnswer("");
          await loadDashboard(cachedMatch.policy_number);
          setMessage("Account profile loaded from saved workspace.");
          return;
        }

        setMessage("No account found for that policy number.");
        return;
      }

      const data = await safeJson(res);
      setProfile(data || {});
      if (data?.policy_number) {
        updateProfileList([data]);
      }
      setCopilotAnswer("");
      await loadDashboard(data?.policy_number);
      setMessage("Account profile loaded.");
    } catch {
      const cachedMatch = getCachedProfiles().find(
        (item) => item?.policy_number === profile.policy_number
      );

      if (cachedMatch) {
        setProfile(cachedMatch);
        setCopilotAnswer("");
        await loadDashboard(cachedMatch.policy_number);
        setMessage("Account profile loaded from saved workspace.");
        return;
      }

      setMessage("Lookup failed.");
    }
  }


// LOSSQ_AUTO_FILL_EXPOSURE_INPUTS_AFTER_UPLOAD_V1
function buildExposureInputsFromUploadedAccount(): AnyObject {
  const sourceProfile: AnyObject = {
    ...(displayProfile || {}),
    ...(profile || {}),
  };

  const derivedFromProfile = deriveExposureInputsFromPolicyRows(sourceProfile);
  const derivedFromPolicySchedule = deriveExposureInputsFromPolicyRows({
    ...(sourceProfile || {}),
    policies: policySchedule || sourceProfile?.policies || [],
  });

  const merged: AnyObject = {
    ...derivedFromProfile,
    ...derivedFromPolicySchedule,
    current_premium:
      sourceProfile?.current_premium ||
      derivedFromProfile?.current_premium ||
      derivedFromPolicySchedule?.current_premium ||
      sourceProfile?.expiring_premium ||
      derivedFromProfile?.expiring_premium ||
      derivedFromPolicySchedule?.expiring_premium ||
      "",
    expiring_premium:
      sourceProfile?.expiring_premium ||
      derivedFromProfile?.expiring_premium ||
      derivedFromPolicySchedule?.expiring_premium ||
      "",
    target_renewal_premium:
      sourceProfile?.target_renewal_premium ||
      derivedFromProfile?.target_renewal_premium ||
      derivedFromPolicySchedule?.target_renewal_premium ||
      "",
    line_of_business:
      sourceProfile?.line_of_business ||
      sourceProfile?.primary_line_of_business ||
      derivedFromProfile?.line_of_business ||
      derivedFromPolicySchedule?.line_of_business ||
      "",
    state:
      sourceProfile?.state ||
      derivedFromProfile?.state ||
      derivedFromPolicySchedule?.state ||
      "",
    class_code:
      sourceProfile?.class_code ||
      sourceProfile?.class_codes ||
      derivedFromProfile?.class_code ||
      derivedFromProfile?.class_codes ||
      derivedFromPolicySchedule?.class_code ||
      derivedFromPolicySchedule?.class_codes ||
      "",
    limits:
      sourceProfile?.limits ||
      sourceProfile?.coverage_limit ||
      derivedFromProfile?.limits ||
      derivedFromProfile?.coverage_limit ||
      derivedFromPolicySchedule?.limits ||
      derivedFromPolicySchedule?.coverage_limit ||
      "",
    deductible:
      sourceProfile?.deductible ||
      derivedFromProfile?.deductible ||
      derivedFromPolicySchedule?.deductible ||
      "",
    retention:
      sourceProfile?.retention ||
      sourceProfile?.sir ||
      derivedFromProfile?.retention ||
      derivedFromPolicySchedule?.retention ||
      "",
    payroll:
      sourceProfile?.payroll ||
      derivedFromProfile?.payroll ||
      derivedFromPolicySchedule?.payroll ||
      "",
    revenue:
      sourceProfile?.revenue ||
      sourceProfile?.sales ||
      sourceProfile?.receipts ||
      derivedFromProfile?.revenue ||
      derivedFromPolicySchedule?.revenue ||
      "",
    sales:
      sourceProfile?.sales ||
      sourceProfile?.revenue ||
      derivedFromProfile?.sales ||
      derivedFromPolicySchedule?.sales ||
      "",
    receipts:
      sourceProfile?.receipts ||
      sourceProfile?.sales ||
      sourceProfile?.revenue ||
      derivedFromProfile?.receipts ||
      derivedFromPolicySchedule?.receipts ||
      "",
    employee_count:
      sourceProfile?.employee_count ||
      sourceProfile?.employeeCount ||
      derivedFromProfile?.employee_count ||
      derivedFromPolicySchedule?.employee_count ||
      "",
    vehicle_count:
      sourceProfile?.vehicle_count ||
      sourceProfile?.vehicleCount ||
      derivedFromProfile?.vehicle_count ||
      derivedFromPolicySchedule?.vehicle_count ||
      "",
    driver_count:
      sourceProfile?.driver_count ||
      sourceProfile?.driverCount ||
      derivedFromProfile?.driver_count ||
      derivedFromPolicySchedule?.driver_count ||
      "",
    property_tiv:
      sourceProfile?.property_tiv ||
      sourceProfile?.tiv ||
      derivedFromProfile?.property_tiv ||
      derivedFromPolicySchedule?.property_tiv ||
      "",
    building_value:
      sourceProfile?.building_value ||
      derivedFromProfile?.building_value ||
      derivedFromPolicySchedule?.building_value ||
      "",
    contents_value:
      sourceProfile?.contents_value ||
      derivedFromProfile?.contents_value ||
      derivedFromPolicySchedule?.contents_value ||
      "",
    square_footage:
      sourceProfile?.square_footage ||
      derivedFromProfile?.square_footage ||
      derivedFromPolicySchedule?.square_footage ||
      "",
    location_count:
      sourceProfile?.location_count ||
      derivedFromProfile?.location_count ||
      derivedFromPolicySchedule?.location_count ||
      "",
    unit_count:
      sourceProfile?.unit_count ||
      derivedFromProfile?.unit_count ||
      derivedFromPolicySchedule?.unit_count ||
      "",
    exposure_basis:
      sourceProfile?.exposure_basis ||
      derivedFromProfile?.exposure_basis ||
      derivedFromPolicySchedule?.exposure_basis ||
      "",
  };

  return Object.fromEntries(
    Object.entries(merged).filter(([, value]) => String(value || "").trim() !== "")
  );
}


  // LOSSQ_EDITABLE_PROFILE_VALUE_PRESERVE_EMPTY_V1
  const editableProfileValue = (field: string) => {
    const profileObject = (profile || {}) as AnyObject;
    const displayObject = (displayProfile || {}) as AnyObject;

    if (Object.prototype.hasOwnProperty.call(profileObject, field)) {
      return String(profileObject[field] ?? "");
    }

    return String(displayObject[field] ?? "");
  };

  // LOSSQ_POLICY_LIMITS_EXPOSURE_BASIS_BLOCK_V2
  const safePolicyLimitsValue = () => {
    const coverageLimit = editableProfileValue("coverage_limit");
    if (coverageLimit) return coverageLimit;

    const rawLimits = editableProfileValue("limits");
    const lowerLimits = rawLimits.toLowerCase();

    const looksLikeExposureBasis =
      lowerLimits.includes("payroll") ||
      lowerLimits.includes("revenue") ||
      lowerLimits.includes("employees") ||
      lowerLimits.includes("vehicles") ||
      lowerLimits.includes("drivers") ||
      lowerLimits.includes("umbrella") ||
      lowerLimits.includes("exposure basis") ||
      lowerLimits.includes("gl limit");

    if (looksLikeExposureBasis) {
      return "";
    }

    return rawLimits;
  };

function autoFillExposureInputsFromUpload() {
  // LOSSQ_EXPOSURE_AUTOFILL_HANDLER_FORCE_UI_UPDATE_V2
  const selectedPolicyForExposure = String(
    profile?.policy_number ||
      safeDisplayProfile?.account_number ||
      displayProfile?.policy_number ||
      displayProfile?.account_number ||
      ""
  ).trim();

  let cachedUpload: any = {};
  try {
    const rawCached = typeof window !== "undefined"
      ? localStorage.getItem(CURRENT_UPLOAD_CACHE_KEY)
      : "";
    cachedUpload = rawCached ? JSON.parse(rawCached) : {};
  } catch {
    cachedUpload = {};
  }

  const sourceProfile: AnyObject = {
    ...(displayProfile || {}),
    ...(profile || {}),
    cached_upload: cachedUpload,
    cached_claims: Array.isArray(cachedUpload) ? cachedUpload : cachedUpload?.claims || cachedUpload?.rows || [],
  };

  const extractedFromCurrentProfile = deriveExposureInputsFromPolicyRows(sourceProfile);
  const extractedFromDisplayProfile = deriveExposureInputsFromPolicyRows(displayProfile || {});
  const extractedFromProfile = deriveExposureInputsFromPolicyRows(profile || {});
  const extractedFromCachedUpload = deriveExposureInputsFromPolicyRows(cachedUpload || {});

  let extracted: AnyObject = {
    ...(typeof buildExposureInputsFromUploadedAccount === "function"
      ? buildExposureInputsFromUploadedAccount()
      : {}),
    ...(extractedFromCachedUpload || {}),
    ...(extractedFromDisplayProfile || {}),
    ...(extractedFromProfile || {}),
    ...(extractedFromCurrentProfile || {}),
  };

  // LOSSQ_EXPOSURE_LINE_OF_BUSINESS_MANUAL_ONLY_V1
  // Do not auto-fill underwriting classification fields from detected claim/policy lines.
  // These must remain manually editable so fallback values like GL/General Liability do not reappear.
  delete extracted.line_of_business;
  delete extracted.primary_line_of_business;
  delete extracted.class_code;
  delete extracted.class_codes;
  delete extracted.state;

  extracted = Object.fromEntries(
    Object.entries(extracted).filter(([, value]) => String(value || "").trim() !== "")
  );

  if (Object.keys(extracted).length === 0) {
    setMessage(
      "No exposure values were found on this profile yet. Re-upload a loss run with labeled exposure fields, or enter the fields manually and click Save Exposure Inputs."
    );
    return;
  }

  let filledCount = 0;

  setProfile((prev: AnyObject) => {
    const next: AnyObject = {
      ...(prev || {}),
      policy_number:
        prev?.policy_number ||
        sourceProfile?.policy_number ||
        selectedPolicyForExposure ||
        "",
      // LOSSQ_EXPOSURE_ACCOUNT_FIELDS_ARE_NOT_POLICY_FIELDS_V2
      account_number: lossqCleanAccountNumber(prev?.account_number || sourceProfile?.account_number),
      customer_number: lossqCleanAccountNumber(
        prev?.customer_number || sourceProfile?.customer_number || sourceProfile?.account_number
      ),
    };

    Object.entries(extracted).forEach(([key, value]) => {
      const clean = String(value || "").trim();
      if (!clean) return;

      if (!String(next[key] || "").trim()) {
        next[key] = clean;
        filledCount += 1;
      }
    });

    return next;
  });

  if (filledCount > 0) {
    setMessage(`Exposure Inputs auto-filled ${filledCount} field(s). Review and click Save Exposure Inputs.`);
  } else {
    setMessage(
      "Exposure values were found, but existing manual values were preserved. Clear a field first if you want Auto-Fill to replace it."
    );
  }
}


async function saveExposureInputs() {
    // LOSSQ_EXPOSURE_INPUTS_BACKEND_SAVE_V1
    const selectedPolicy =
      profile?.policy_number ||
      safeDisplayProfile?.account_number ||
      safeDisplayProfile?.customer_number ||
      getCachedSelectedPolicy();

    const extractedExposure = deriveExposureInputsFromPolicyRows(profile);

    const autoExposureOnlyForBlankFields = Object.fromEntries(
      Object.entries(extractedExposure || {}).filter(([key, value]) => {
        return String(value || "").trim() && !String(profile?.[key] || "").trim();
      })
    );

    const nextProfile = {
      ...profile,
      ...autoExposureOnlyForBlankFields,
      policy_number: profile?.policy_number || selectedPolicy || "",
      // LOSSQ_SAVE_EXPOSURE_ACCOUNT_FIELDS_ARE_NOT_POLICY_FIELDS_V2
      account_number: lossqCleanAccountNumber(safeDisplayProfile?.account_number),
      customer_number: lossqCleanAccountNumber(
        safeDisplayProfile?.customer_number || safeDisplayProfile?.account_number
      ),
    };

    if (
      !nextProfile.policy_number &&
      !nextProfile.account_number &&
      !nextProfile.customer_number
    ) {
      setMessage("Select or upload an account before saving exposure inputs.");
      return;
    }

    setProfile(nextProfile);
    updateProfileList([nextProfile]);

    if (selectedPolicy) {
      setCachedSelectedPolicy(selectedPolicy);
    }

    try {
      setMessage("Saving manual exposure inputs...");

      const res = await fetch(`${API}/account-profile/`, {
        method: "PUT",
        headers: {
          ...authHeaders(),
          "Content-Type": "application/json",
        },
        body: JSON.stringify(nextProfile),
      });

      if (res.status === 401 || res.status === 403) {
        clearSession();
        router.replace("/login?expired=1");
        return;
      }

      if (!res.ok) {
        const errorData = await safeJson(res);
        throw new Error(errorData?.detail || "Backend exposure save failed.");
      }

      const savedData = await safeJson(res);
      const savedProfile =
        savedData && typeof savedData === "object"
          ? {
              ...nextProfile,
              ...savedData,
            }
          : nextProfile;

      setProfile(savedProfile);
      updateProfileList([savedProfile]);

      const savedPolicy =
        savedProfile?.policy_number ||
        savedProfile?.account_number ||
        savedProfile?.customer_number ||
        selectedPolicy;

      if (savedPolicy) {
        setCachedSelectedPolicy(savedPolicy);
      }

      changeActiveTool("exposure-inputs");
      setMessage("Exposure inputs saved to this account profile. They will remain after refresh and login.");
    } catch (error: any) {
      updateProfileList([nextProfile]);
      setMessage(
        error?.message ||
          "Exposure inputs saved locally, but backend save failed."
      );
    }
  }

  async function uploadFiles() {

    // LOSSQ_CLEAR_STALE_CLAIM_CACHE_ON_UPLOAD_V1
    try {
      setClaims(lossqFilterRealClaims([]));
      setSelectedClaimDetail(null);
      setCachedCurrentUpload({});

      if (typeof window !== "undefined") {
        Object.keys(localStorage)
          .filter((key) =>
            key.toLowerCase().includes("lossq") &&
            (
              key.toLowerCase().includes("claim") ||
              key.toLowerCase().includes("upload") ||
              key.toLowerCase().includes("policy") ||
              key.toLowerCase().includes("dashboard")
            )
          )
          .forEach((key) => localStorage.removeItem(key));

        Object.keys(sessionStorage)
          .filter((key) =>
            key.toLowerCase().includes("lossq") &&
            (
              key.toLowerCase().includes("claim") ||
              key.toLowerCase().includes("upload") ||
              key.toLowerCase().includes("policy") ||
              key.toLowerCase().includes("dashboard")
            )
          )
          .forEach((key) => sessionStorage.removeItem(key));
      }
    } catch (cacheClearError) {
      console.warn("LossQ stale upload cache cleanup skipped", cacheClearError);
    }

if (isUploading) return;
  const selectedFiles = files ? Array.from(files) : [];
  if (selectedFiles.length === 0) {
    setMessage("Please select one or more PDF, Excel, or CSV files first.");
    return;
  }
  try {
    // LOSSQ_UPLOAD_PROFILE_ISOLATION_V1
    // Prevent old profile/policy rows from bleeding into a newly uploaded account.
    clearCachedCurrentUpload();
    clearCachedSelectedClaim();
    localStorage.removeItem("lossq_last_upload_review");

    setIsUploading(true);
    clearCachedLastUploadReview();
    clearCachedCurrentUpload();
    setMessage("Uploading and analyzing loss runs with V2 parser...");

     const uploadResults: any[] = [];

    /*
      IMPORTANT:
      Universal OCR + Document Intelligence V2 currently accepts one file at a time.
      For multiple files, we upload each file through /upload/loss-run separately.
      Do not force the old selected policy number into a new upload.
      The parser should decide the account number, policy schedule, and claim policies.
    */

    for (const file of selectedFiles) {
      const formData = new FormData();
      formData.append("file", file);

      const res = await fetch(`${API}/upload/loss-run`, {
        method: "POST",
        headers: authHeaders(),
        body: formData,
      });

      const data = await safeJson(res);
      // LOSSQ_FRONTEND_UPLOAD_ROOT_CAUSE_DEBUG_V1
      console.log("LOSSQ_FRONTEND_UPLOAD_RESPONSE_DEBUG", {
        status: res.status,
        ok: res.ok,
        data,
      });

      if (res.status === 401 || res.status === 403) {
        clearSession();
        router.replace("/login?expired=1");
        return;
      }

      if (!res.ok) {
        setMessage(`Upload failed. Backend returned ${res.status}: ${JSON.stringify(data)}`);
        return;
      }

      uploadResults.push(data);
    }

    const primaryData = uploadResults[uploadResults.length - 1] || {};

    const allUploadProfiles = uploadResults
      .map((item) => item?.profile || item?.account_profile || item?.accountProfile || {})
      .filter((item) => item && typeof item === "object");

    const mergedUploadProfile = allUploadProfiles.reduce((acc: any, item: any) => {
      Object.entries(item || {}).forEach(([key, value]) => {
        if (
          value !== "" &&
          value !== null &&
          value !== undefined &&
          !(Array.isArray(value) && value.length === 0)
        ) {
          if (key === "policies") {
            acc.policies = [
              ...(Array.isArray(acc.policies) ? acc.policies : []),
              ...(Array.isArray(value) ? value : []),
            ];
          } else if (!acc[key] || isBadPolicyNumberValue(acc[key])) {
            acc[key] = value;
          }
        }
      });

      return acc;
    }, {});

    const mergedAccountKey = chooseSafePolicyNumber(
      mergedUploadProfile?.account_number,
      mergedUploadProfile?.customer_number,
      primaryData?.account_number,
      primaryData?.customer_number,
      primaryData?.account_safeDisplayProfile?.account_number,
      primaryData?.account_safeDisplayProfile?.customer_number,
      primaryData?.safeDisplayProfile?.account_number,
      primaryData?.safeDisplayProfile?.customer_number
    );

    const universalUploadPolicyDates = getUniversalUploadPolicyDates(
      uploadResults,
      primaryData,
      mergedUploadProfile,
      allUploadProfiles
    );

    const primaryProfile = {
      ...mergedUploadProfile,
      // LOSSQ_PRIMARY_PROFILE_ACCOUNT_FIELDS_ARE_NOT_POLICY_FIELDS_V2
      account_number: lossqCleanAccountNumber(mergedUploadProfile?.account_number),
      customer_number: lossqCleanAccountNumber(
        mergedUploadProfile?.customer_number || mergedUploadProfile?.account_number
      ),
      policy_number: mergedAccountKey || chooseSafePolicyNumber(mergedUploadProfile?.policy_number) || "",

      effective_date:
        mergedUploadProfile?.effective_date ||
        mergedUploadProfile?.policy_effective_date ||
        primaryData?.effective_date ||
        primaryData?.policy_effective_date ||
        primaryData?.account_profile?.effective_date ||
        primaryData?.profile?.effective_date ||
        universalUploadPolicyDates.effective_date ||
        "",

      policy_effective_date:
        mergedUploadProfile?.policy_effective_date ||
        mergedUploadProfile?.effective_date ||
        universalUploadPolicyDates.effective_date ||
        "",

      expiration_date:
        mergedUploadProfile?.expiration_date ||
        mergedUploadProfile?.policy_expiration_date ||
        primaryData?.expiration_date ||
        primaryData?.policy_expiration_date ||
        primaryData?.account_profile?.expiration_date ||
        primaryData?.profile?.expiration_date ||
        universalUploadPolicyDates.expiration_date ||
        "",

      policy_expiration_date:
        mergedUploadProfile?.policy_expiration_date ||
        mergedUploadProfile?.expiration_date ||
        universalUploadPolicyDates.expiration_date ||
        "",

      valuation_date:
        mergedUploadProfile?.valuation_date ||
        mergedUploadProfile?.loss_run_valuation_date ||
        primaryData?.valuation_date ||
        primaryData?.loss_run_valuation_date ||
        primaryData?.evaluation_date ||
        primaryData?.account_profile?.valuation_date ||
        primaryData?.profile?.valuation_date ||
        universalUploadPolicyDates.valuation_date ||
        "",

      loss_run_valuation_date:
        mergedUploadProfile?.loss_run_valuation_date ||
        mergedUploadProfile?.valuation_date ||
        universalUploadPolicyDates.valuation_date ||
        "",

      evaluation_date:
        mergedUploadProfile?.evaluation_date ||
        mergedUploadProfile?.valuation_date ||
        universalUploadPolicyDates.valuation_date ||
        "",
    };
    const uploadedFileNames = selectedFiles.map((file) => file.name).join(", ");

    const combinedClaims = uploadResults.flatMap((item) =>
      firstNonEmptyArray(
        item?.saved_claim_rows,
        item?.claims,
        item?.parsed_claims,
        item?.claim_rows,
        item?.normalized_claims
      )
    );

    const combinedPolicies = uploadResults.flatMap((item) =>
      firstNonEmptyArray(
        item?.policies,
        item?.profile?.policies,
        item?.account_profile?.policies
      )
    );

    const totalSavedClaims = uploadResults.reduce(
      (sum, item) => sum + Number(item?.saved_claims || item?.claim_count || 0),
      0
    );

    if (typeof window !== "undefined") {
      localStorage.setItem(
        "lossq_last_upload_review",
        JSON.stringify({
          uploaded_at: new Date().toISOString(),
          uploaded_files: uploadResults.flatMap((item) => item?.uploaded_files || []).length
            ? uploadResults.flatMap((item) => item?.uploaded_files || [])
            : selectedFiles.map((file) => file.name),
          profile: {
            ...(primaryProfile || {}),
            ...((allUploadProfiles || []).reduce((acc: any, item: any) => ({ ...acc, ...(item || {}) }), {})),
          },
          policies: lossqForceDatesOntoPolicyRows(combinedPolicies, {
            effective_date:
              mergedUploadProfile?.effective_date ||
              mergedUploadProfile?.policy_effective_date ||
              universalUploadPolicyDates.effective_date ||
              "",
            policy_effective_date:
              mergedUploadProfile?.policy_effective_date ||
              mergedUploadProfile?.effective_date ||
              universalUploadPolicyDates.effective_date ||
              "",
            expiration_date:
              mergedUploadProfile?.expiration_date ||
              mergedUploadProfile?.policy_expiration_date ||
              universalUploadPolicyDates.expiration_date ||
              "",
            policy_expiration_date:
              mergedUploadProfile?.policy_expiration_date ||
              mergedUploadProfile?.expiration_date ||
              universalUploadPolicyDates.expiration_date ||
              "",
            valuation_date:
              mergedUploadProfile?.valuation_date ||
              mergedUploadProfile?.evaluation_date ||
              mergedUploadProfile?.loss_run_valuation_date ||
              universalUploadPolicyDates.valuation_date ||
              "",
            evaluation_date:
              mergedUploadProfile?.evaluation_date ||
              mergedUploadProfile?.valuation_date ||
              universalUploadPolicyDates.valuation_date ||
              "",
          }),
          // LOSSQ_BACKEND_TRUTH_CLAIM_ROWS_V2
          // Do not cache upload response claim rows. Backend /claims is authoritative.
          claims: [],
          saved_claim_rows: [],
          validation: primaryData?.validation || primaryProfile?.validation || {},
          saved_claims: totalSavedClaims,
          raw_response: uploadResults.length === 1 ? primaryData : uploadResults,
        })
      );
    }

    setMessage(
      `Upload complete using V2 parser. Saved ${totalSavedClaims} claim(s). New file(s): ${uploadedFileNames}`
    );

    window.setTimeout(() => {
      setMessage((current) =>
        current.startsWith("Upload complete using V2 parser") ? "" : current
      );
    }, 5000);

    if (primaryProfile && Object.keys(primaryProfile).length > 0) {
      const claimPolicyNumbers = Array.from(
        new Set(
          combinedClaims
            .map((claim: any) => claim?.policy_number || claim?.policyNumber || claim?.policy_no)
            .map((item: any) => normalizePolicyNumber(item))
            .filter(Boolean)
        )
      );

      const uploadDateSource = getUniversalUploadPolicyDates(
        uploadResults,
        primaryData,
        primaryProfile,
        allUploadProfiles,
        combinedClaims
      );

      const fallbackPolicies = claimPolicyNumbers.map((policyNumber) => ({
        policy_type: "Uploaded Loss Run",
        policy_number: policyNumber,
        carrier: primaryProfile?.carrier_name || primaryProfile?.writing_carrier || "",
        effective_date:
          primaryProfile?.effective_date ||
          primaryProfile?.policy_effective_date ||
          uploadDateSource.effective_date ||
          "",
        policy_effective_date:
          primaryProfile?.policy_effective_date ||
          primaryProfile?.effective_date ||
          uploadDateSource.effective_date ||
          "",
        expiration_date:
          primaryProfile?.expiration_date ||
          primaryProfile?.policy_expiration_date ||
          uploadDateSource.expiration_date ||
          "",
        policy_expiration_date:
          primaryProfile?.policy_expiration_date ||
          primaryProfile?.expiration_date ||
          uploadDateSource.expiration_date ||
          "",
        valuation_date:
          primaryProfile?.valuation_date ||
          primaryProfile?.evaluation_date ||
          primaryProfile?.loss_run_valuation_date ||
          uploadDateSource.valuation_date ||
          "",
        evaluation_date:
          primaryProfile?.evaluation_date ||
          primaryProfile?.valuation_date ||
          uploadDateSource.valuation_date ||
          "",
      }));

      const uploadRawText =
      primaryData?.raw_text_preview ||
      primaryData?.raw_text ||
      primaryData?.text ||
      primaryProfile?.raw_text_preview ||
      primaryProfile?.raw_text ||
      "";

    const extractedExposureInputs = extractExposureInputsFromUploadText(uploadRawText);

    const cleanCarrierName = chooseCleanCarrier(
      primaryProfile?.carrier_name,
      primaryProfile?.writing_carrier,
      primaryData?.carrier_name,
      primaryData?.writing_carrier,
      primaryData?.account_profile?.carrier_name,
      primaryData?.account_profile?.writing_carrier
    );

    const uploadedProfile = {
        ...primaryProfile,
        ...extractedExposureInputs,
        carrier_name: cleanCarrierName || primaryProfile?.carrier_name || "",
        writing_carrier: cleanCarrierName || primaryProfile?.writing_carrier || primaryProfile?.carrier_name || "",

        // LOSSQ_UNIVERSAL_UPLOAD_PROFILE_DATE_ALIAS_CARRY_FORWARD_V1
        effective_date:
          primaryProfile?.effective_date ||
          primaryProfile?.policy_effective_date ||
          primaryData?.effective_date ||
          primaryData?.policy_effective_date ||
          primaryData?.account_profile?.effective_date ||
          primaryData?.profile?.effective_date ||
          "",

        expiration_date:
          primaryProfile?.expiration_date ||
          primaryProfile?.policy_expiration_date ||
          primaryData?.expiration_date ||
          primaryData?.policy_expiration_date ||
          primaryData?.account_profile?.expiration_date ||
          primaryData?.profile?.expiration_date ||
          "",

        valuation_date:
          primaryProfile?.valuation_date ||
          primaryProfile?.loss_run_valuation_date ||
          primaryData?.valuation_date ||
          primaryData?.loss_run_valuation_date ||
          primaryData?.evaluation_date ||
          primaryData?.account_profile?.valuation_date ||
          primaryData?.profile?.valuation_date ||
          "",

        insured:
          primaryProfile?.insured ||
          primaryProfile?.business_name ||
          primaryProfile?.named_insured ||
          primaryData?.business_name ||
          "",

        business_name:
          primaryProfile?.business_name ||
          primaryProfile?.insured ||
          primaryProfile?.named_insured ||
          primaryData?.business_name ||
          "",

        policy_number:
          primaryProfile?.policy_number ||
          primaryProfile?.account_number ||
          claimPolicyNumbers[0] ||
          "",

        policies: firstNonEmptyArray(
          primaryData?.policies,
          primaryProfile?.policies,
          primaryData?.account_profile?.policies,
          combinedPolicies,
          fallbackPolicies
        ),

        validation: primaryData?.validation || primaryProfile?.validation || {},
      };


      const safeUploadedProfilePolicy = chooseSafePolicyNumber(
        mergedUploadProfile?.account_number,
        mergedUploadProfile?.customer_number,
        mergedUploadProfile?.policy_number,
        primaryData?.account_safeDisplayProfile?.account_number,
        primaryData?.account_safeDisplayProfile?.customer_number,
        primaryData?.selected_policy_number,
        primaryData?.policy_number
      );

      if (safeUploadedProfilePolicy) {
        uploadedProfile.policy_number = safeUploadedProfilePolicy;
      }

      // LOSSQ_UPLOAD_ACCOUNT_FIELDS_ARE_NOT_POLICY_FIELDS_V2
      uploadedProfile.account_number = lossqCleanAccountNumber(uploadedProfile.account_number);
      uploadedProfile.customer_number = lossqCleanAccountNumber(
        uploadedProfile.customer_number || uploadedProfile.account_number
      );


      // LOSSQ_UPLOAD_PROFILE_FINAL_NORMALIZATION
      const safeMainAccountKey = chooseSafePolicyNumber(
        mergedUploadProfile?.account_number,
        mergedUploadProfile?.customer_number,
        primaryProfile?.account_number,
        primaryProfile?.customer_number,
        primaryData?.account_number,
        primaryData?.customer_number,
        primaryData?.account_safeDisplayProfile?.account_number,
        primaryData?.account_safeDisplayProfile?.customer_number,
        mergedUploadProfile?.policy_number
      );

      if (safeMainAccountKey) {
        uploadedProfile.policy_number = safeMainAccountKey;
      }

      // LOSSQ_UPLOAD_PROFILE_ACCOUNT_NUMBER_DISPLAY_FIX_V1
      // Do not display or cache policy numbers as account/customer numbers.
      uploadedProfile.account_number = lossqCleanAccountNumber(uploadedProfile.account_number);
      uploadedProfile.customer_number = lossqCleanAccountNumber(
        uploadedProfile.customer_number || uploadedProfile.account_number
      );
      console.log("LOSSQ_FRONTEND_UPLOADED_PROFILE_DEBUG", {
        account_number: uploadedProfile.account_number,
        customer_number: uploadedProfile.customer_number,
        policy_number: uploadedProfile.policy_number,
        main_policy: uploadedProfile.main_policy,
        policy_numbers: uploadedProfile.policy_numbers,
        policies: uploadedProfile.policies,
        claims: uploadedProfile.claims,
        parsed_claims: uploadedProfile.parsed_claims,
      });

      uploadedProfile.evaluation_date = getBestEvaluationDate(uploadedProfile);


      resetProfileAnalyticsState({
        setSummary,
        setDecision,
        setCarrierAppetite,
        setSubmissionReadiness,
        setCarrierMatch,
        setPremiumForecast,
        setSubmissionBuilder,
        setTimeline,
setLazyLoadedTools,
        setLazyToolLoading,
      });
      setBlankWorkspaceMode(false);
      uploadedProfile.account_number = lossqCleanAccountNumber(uploadedProfile.account_number);
      uploadedProfile.customer_number = lossqCleanAccountNumber(uploadedProfile.customer_number);
      setProfile(uploadedProfile);

      // LOSSQ_RELOAD_BACKEND_CLAIMS_AFTER_UPLOAD_V1
      // Upload response intentionally does not carry claim rows.
      // Backend /claims is authoritative, so reload dashboard claims immediately.
      const uploadedPolicyForClaimsReload = chooseSafePolicyNumber(
        uploadedProfile?.policy_number,
        ...(Array.isArray(uploadedProfile?.policies)
          ? uploadedProfile.policies.map((p: any) => p?.policy_number)
          : [])
      );

      if (uploadedPolicyForClaimsReload) {
        const uploadClaimPolicyKeys = Array.from(
          new Set(
            [
              uploadedPolicyForClaimsReload,
              ...(Array.isArray(uploadedProfile?.policies)
                ? uploadedProfile.policies.map((p: any) => p?.policy_number)
                : []),
            ]
              .map((item: any) => normalizePolicyNumber(item))
              .filter(Boolean)
          )
        );

        const uploadClaimsUrl =
          uploadClaimPolicyKeys.length > 0
            ? `${API}/claims/?policy_numbers=${encodeURIComponent(uploadClaimPolicyKeys.join(","))}`
            : `${API}/claims/`;

        console.log("LOSSQ_FRONTEND_RELOAD_CLAIMS_AFTER_UPLOAD", {
          uploadedPolicyForClaimsReload,
          uploadClaimPolicyKeys,
          uploadClaimsUrl,
          policies: uploadedProfile?.policies,
        });

        const uploadClaimsResponse = await fetch(uploadClaimsUrl, {
          headers: {
            Authorization: `Bearer ${getToken() || ""}`,
          },
        });

        const uploadClaimsJson: any[] = uploadClaimsResponse.ok
          ? await uploadClaimsResponse.json()
          : [];

        const uploadCleanClaims = lossqFilterRealClaims(uploadClaimsJson);

        // LOSSQ_DIRECT_SET_CLAIMS_AFTER_UPLOAD_V1
        console.log("LOSSQ_FRONTEND_DIRECT_CLAIMS_AFTER_UPLOAD", {
          ok: uploadClaimsResponse.ok,
          status: uploadClaimsResponse.status,
          rawCount: Array.isArray(uploadClaimsJson) ? uploadClaimsJson.length : 0,
          cleanedCount: Array.isArray(uploadCleanClaims) ? uploadCleanClaims.length : 0,
          sample: Array.isArray(uploadCleanClaims) ? uploadCleanClaims.slice(0, 3) : [],
        });

        setClaims(uploadCleanClaims);
      }

      // Uploaded profile becomes the active authority for this account.
      // This keeps old old/previous policy rows from appearing inside a new upload's schedule.
      setCachedProfiles([
        uploadedProfile,
        ...getCachedProfiles().filter((item: any) => {
          const uploadedKeys = [
            mergedUploadProfile?.policy_number,
            mergedUploadProfile?.account_number,
            mergedUploadProfile?.customer_number,
          ]
            .map((key: any) => normalizePolicyNumber(key))
            .filter(Boolean);

          const itemKeys = [
            item?.policy_number,
            item?.account_number,
            item?.customer_number,
          ]
            .map((key: any) => normalizePolicyNumber(key))
            .filter(Boolean);

          return !itemKeys.some((key: string) => uploadedKeys.includes(key));
        }),
      ]);

      updateProfileList([uploadedProfile]);
    }

    // Show the freshly parsed claim rows immediately. loadDashboard may fetch
    // LOSSQ_BACKEND_TRUTH_CLAIM_ROWS_V2: do not overwrite backend claims with upload response rows.

    const uploadedPolicyNumber = chooseSafePolicyNumber(
      primaryProfile?.account_number,
      primaryProfile?.customer_number,
      mergedAccountKey,
      primaryData?.account_number,
      primaryData?.customer_number,
      primaryData?.account_safeDisplayProfile?.account_number,
      primaryData?.account_safeDisplayProfile?.customer_number,
      primaryData?.safeDisplayProfile?.account_number,
      primaryData?.safeDisplayProfile?.customer_number,
      primaryProfile?.policy_number,
      primaryData?.account_profile?.policy_number,
      primaryData?.profile?.policy_number,
      primaryData?.selected_policy_number,
      primaryData?.policy_number,
      combinedPolicies.find((item: any) => item?.policy_number)?.policy_number,
      combinedClaims.find((claim: any) => claim?.policy_number || claim?.policyNumber || claim?.policy_no)?.policy_number
    );

    const uploadPolicySet = Array.from(
      new Set(
        [
          uploadedPolicyNumber,
          ...combinedPolicies.map((item: any) => item?.policy_number),
          ...combinedClaims.map((claim: any) => claim?.policy_number || claim?.policyNumber || claim?.policy_no),
        ]
          .map((item: any) => normalizePolicyNumber(item))
          .filter(Boolean)
      )
    );



    // LOSSQ_FORCE_COMBINED_POLICY_DATES_V1
    const forcedUploadDates = getUniversalUploadPolicyDates(
      uploadResults,
      primaryData,
      primaryProfile,
      allUploadProfiles,
      combinedPolicies,
      combinedClaims
    );

    const forcedDateSource = {
      effective_date:
        mergedUploadProfile?.effective_date ||
        mergedUploadProfile?.policy_effective_date ||
        forcedUploadDates.effective_date ||
        "",
      policy_effective_date:
        mergedUploadProfile?.policy_effective_date ||
        mergedUploadProfile?.effective_date ||
        forcedUploadDates.effective_date ||
        "",
      expiration_date:
        mergedUploadProfile?.expiration_date ||
        mergedUploadProfile?.policy_expiration_date ||
        forcedUploadDates.expiration_date ||
        "",
      policy_expiration_date:
        mergedUploadProfile?.policy_expiration_date ||
        mergedUploadProfile?.expiration_date ||
        forcedUploadDates.expiration_date ||
        "",
      valuation_date:
        mergedUploadProfile?.valuation_date ||
        mergedUploadProfile?.evaluation_date ||
        mergedUploadProfile?.loss_run_valuation_date ||
        forcedUploadDates.valuation_date ||
        "",
      evaluation_date:
        mergedUploadProfile?.evaluation_date ||
        mergedUploadProfile?.valuation_date ||
        forcedUploadDates.valuation_date ||
        "",
    };

    const dateForcedPolicies = lossqForceDatesOntoPolicyRows(combinedPolicies, forcedDateSource);

    const currentUploadSnapshot = {
      uploaded_at: new Date().toISOString(),
      policy_number: normalizePolicyNumber(uploadedPolicyNumber),
      policy_numbers: uploadPolicySet,
      profile: {
        ...(primaryProfile || {}),
        ...((allUploadProfiles || []).reduce((acc: any, item: any) => ({ ...acc, ...(item || {}) }), {})),
      },
      policies: combinedPolicies,
      claims: combinedClaims,
      saved_claim_rows: combinedClaims,
      validation: primaryData?.validation || primaryProfile?.validation || {},
    };
    // LOSSQ_BACKEND_TRUTH_AFTER_UPLOAD_V1
    // Do not cache upload claim rows here. Reload from backend DB after upload.
    clearCachedCurrentUpload();
    clearCachedLastUploadReview();

    if (uploadedPolicyNumber) {
      setCachedSelectedPolicy(uploadedPolicyNumber);
      // LOSSQ_CLEAR_UPLOAD_CLAIM_CACHE_BEFORE_RELOAD_V2
    clearCachedCurrentUpload();
    clearCachedLastUploadReview();
    await loadDashboard(uploadedPolicyNumber);
    } else {
      await loadDashboard();
    }
    // LOSSQ_BACKEND_TRUTH_AFTER_UPLOAD_V1
    // Do not overwrite backend-loaded claims with upload response rows.

    setActiveTool("overview");

    window.setTimeout(() => {
      setMessage((current) =>
        current.includes("Upload complete using V2 parser") ? "" : current
      );
    }, 6000);
  } catch (error: any) {
    setMessage(
      `Upload failed before completion. Backend may have crashed. Error: ${
        error?.message || "Unknown error"
      }`
    );
  } finally {
    setIsUploading(false);
  }
}

async function downloadPdf(url: string, filename: string, init?: RequestInit) {
  const baseHeaders: Record<string, string> = {
    ...authHeaders(),
  };

  const initHeaders = (init?.headers || {}) as Record<string, string>;

  const res = await fetch(url, {
    ...init,
    headers: {
      ...baseHeaders,
      ...initHeaders,
    },
  });

  if (res.status === 401 || res.status === 403) {
    clearSession();
    router.replace("/login?expired=1");
    return;
  }

  if (!res.ok) {
    let errorText = "";
    try {
      errorText = await res.text();
    } catch {
      errorText = "";
    }

    const shortError = errorText ? errorText.slice(0, 300) : "";
    throw new Error(`Report export failed with status ${res.status}. ${shortError}`);
  }

  const blob = await res.blob();
  const objectUrl = window.URL.createObjectURL(blob);

  const a = document.createElement("a");
  a.href = objectUrl;
  a.download = filename;
  a.click();

  window.URL.revokeObjectURL(objectUrl);
}



// LOSSQ_REPORT_CURRENT_ACCOUNT_ONLY_FRONTEND_V1
function lossqReportPolicyNumbersFromProfile(profileLike: any): string[] {
  const values: string[] = [];

  const add = (value: any) => {
    const normalized = normalizePolicyNumber(value);
    if (normalized && !values.includes(normalized)) values.push(normalized);
  };

  add(profileLike?.policy_number);
  add(profileLike?.account_number);
  add(profileLike?.customer_number);

  const policies = Array.isArray(profileLike?.policies) ? profileLike.policies : [];
  policies.forEach((policy: any) => {
    add(policy?.policy_number);
    add(policy?.policyNumber);
    add(policy?.policy_no);
    add(policy?.policy);
  });

  return values;
}

function lossqFilterReportClaimsToCurrentAccount(rows: any[], policyNumbers: string[]): any[] {
  const policySet = new Set((policyNumbers || []).map((item) => normalizePolicyNumber(item)).filter(Boolean));
  if (policySet.size === 0) return [];

  return lossqFilterRealClaims(Array.isArray(rows) ? rows : []).filter((claim: any) => {
    const claimPolicy = normalizePolicyNumber(
      claim?.policy_number ||
      claim?.policyNumber ||
      claim?.policy_no ||
      claim?.policy ||
      claim?.profile_policy_number ||
      claim?.selected_policy_number ||
      claim?.account_number ||
      claim?.customer_number
    );
    return claimPolicy && policySet.has(claimPolicy);
  });
}


function buildReportQuery() {
  const params = new URLSearchParams();

  const reportProfileId = profile?.id || displayProfile?.id || activeProfileRef.current?.id;
  if (reportProfileId) {
    params.set("profile_id", String(reportProfileId));
  }

  if (profile?.policy_number) {
    params.set("policy_number", profile.policy_number);
  }

  if (safeDisplayProfile?.account_number) {
    params.set("account_number", profile.account_number);
  }

  if (safeDisplayProfile?.customer_number) {
    params.set("customer_number", profile.customer_number);
  }

  const query = params.toString();
  return query ? `?${query}` : "";
}




function buildReportPayload() {
  const currentUpload = getCachedCurrentUpload();
  const cachedUpload = getCachedLastUploadReview();

  const currentUploadClaims = Array.isArray(currentUpload?.claims) ? currentUpload.claims : [];
  const cachedUploadClaims = Array.isArray(cachedUpload?.claims) ? cachedUpload.claims : [];

  const currentUploadPolicies = new Set(
    (Array.isArray(currentUpload?.policy_numbers) ? currentUpload.policy_numbers : [])
      .map((item: any) => normalizePolicyNumber(item))
      .filter(Boolean)
  );

  const currentUploadApplies =
    currentUploadClaims.length > 0 &&
    (activePolicyNumbers.length === 0 && currentUploadClaims.length > 0) ||
    activePolicyNumbers.some((policyNumber) => currentUploadPolicies.has(policyNumber));

  const reportClaims =
    currentUploadApplies
      ? currentUploadClaims
      : visibleClaims.length > 0
      ? visibleClaims
      : claims.length > 0
      ? claims
      : cachedUploadClaims;

  const claimPolicyNumbers = Array.from(
    new Set(
      reportClaims
        .map((claim: any) => claim?.policy_number || claim?.policyNumber || claim?.policy_no)
        .map((item: any) => normalizePolicyNumber(item))
        .filter(Boolean)
    )
  );

  const policyNumbersForReport =
    activePolicyNumbers.length > 0 ? activePolicyNumbers : claimPolicyNumbers;

  // LOSSQ_REPORT_PAYLOAD_SCOPE_FIX_V1
  const safeCurrentReportProfile =
    displayProfile ||
    profile ||
    activeProfileRef.current ||
    currentUpload?.profile ||
    cachedUpload?.profile ||
    {};

  const safeCurrentReportPolicyNumbers = Array.from(
    new Set([
      ...lossqReportPolicyNumbersFromProfile(safeCurrentReportProfile),
      ...lossqReportPolicyNumbersFromProfile(profile),
      ...lossqReportPolicyNumbersFromProfile(activeProfileRef.current),
      ...(Array.isArray(activePolicyNumbers) ? activePolicyNumbers : []),
    ].map((item) => normalizePolicyNumber(item)).filter(Boolean))
  );

  return {
    profile: safeCurrentReportProfile,
    claims: reportClaims,
    summary: effectiveSummary || summary || {},
    decision: effectiveDecision || decision || {},
    carrier_appetite: effectiveCarrierAppetite || carrierAppetite || {},
    carrier_match: effectiveCarrierMatch || carrierMatch || {},
    premium_forecast: effectivePremiumForecast || premiumForecast || {},
    submission_readiness: effectiveSubmissionReadiness || submissionReadiness || {},
    policy_numbers_used: safeCurrentReportPolicyNumbers.length > 0 ? safeCurrentReportPolicyNumbers : policyNumbersForReport,
    profile_id: profile?.id || displayProfile?.id || null,
  };
}


async function exportCarrierLossRun() {
  const query = buildReportQuery();

  await downloadPdf(
    `${API}/reports/loss-run-template-pdf${query}`,
    "lossq_carrier_loss_run.pdf"
  );
}


  async function exportExecutiveReport() {
    if (!canUseFeature("pdf_exports")) {
      setMessage("PDF exports are not included in the current package.");
      return;
    }

  const query = buildReportQuery();

  setMessage("Generating executive underwriting report...");

  await downloadPdf(
    `${API}/reports/executive-report-pdf${query}`,
    "lossq_executive_underwriting_report.pdf",
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(buildReportPayload()),
    }
  );

  setMessage("Executive underwriting report generated.");
}


  async function generateRenewalMemo() {
    const selectedPolicy =
      displayProfile?.policy_number ||
      profile?.policy_number ||
      displayProfile?.account_number ||
      safeDisplayProfile?.account_number ||
      displayProfile?.customer_number ||
      safeDisplayProfile?.customer_number ||
      getCachedSelectedPolicy();

    const selectedName =
      displayProfile?.business_name ||
      displayProfile?.insured ||
      profile?.business_name ||
      profile?.insured ||
      "Selected Account";

    if (!selectedPolicy && visibleClaims.length === 0) {
      setRenewalMemo("Select a policy/account or upload claims first.");
      return;
    }

    setMemoLoading(true);
    setRenewalMemo(`Generating renewal memo for ${selectedPolicy || selectedName}...`);

    const buildLocalMemo = () => {
      const claimsUsed = visibleClaims.length || claims.length || 0;
      const openCount = openClaims || 0;
      const incurred = Number(totalIncurred || 0).toLocaleString();
      const reserve = Number(totalReserve || 0).toLocaleString();
      const riskLevel = effectiveSummary?.renewal_risk_level || localRenewalRiskLevel || "Needs Review";
      const score = effectiveSummary?.renewal_score ?? localRenewalScore ?? "Not Rated";
      const drivers = Array.isArray(effectiveSummary?.renewal_drivers)
        ? effectiveSummary.renewal_drivers
        : localRenewalDrivers || [];
      const concerns = Array.isArray(effectiveSummary?.carrier_concerns)
        ? effectiveSummary.carrier_concerns
        : [];

      return [
        `LOSSQ AI RENEWAL MEMO`,
        ``,
        `Account: ${selectedName}`,
        `Policy / Account Number: ${selectedPolicy || "Not Set"}`,
        `Renewal Score: ${score}`,
        `Renewal Risk Level: ${riskLevel}`,
        `Claims Reviewed: ${claimsUsed}`,
        `Open Claims: ${openCount}`,
        `Total Incurred: $${incurred}`,
        `Total Reserve: $${reserve}`,
        ``,
        `Executive Summary`,
        effectiveSummary?.renewal_summary ||
          `LossQ reviewed the loaded claim activity for ${selectedName}. The account currently reflects ${claimsUsed} claim(s), ${openCount} open claim(s), and $${incurred} in total incurred losses. Renewal risk is ${riskLevel}.`,
        ``,
        `Renewal Drivers`,
        ...(drivers.length ? drivers.map((item: any) => `- ${item}`) : [`- Claims loaded for underwriting review.`]),
        ``,
        `Carrier Concerns`,
        ...(concerns.length ? concerns.map((item: any) => `- ${item}`) : [`- Confirm open claim status, reserve adequacy, and corrective-action documentation before carrier submission.`]),
        ``,
        `Broker Recommendation`,
        effectiveSummary?.broker_recommendation ||
          `Prepare updated loss runs, explain open claims, confirm reserves, document corrective actions, and include a clear broker narrative before approaching renewal markets.`,
      ].join("\n");
    };

    try {
      const policy = selectedPolicy
        ? `?policy_number=${encodeURIComponent(selectedPolicy)}`
        : "";

      const res = await fetch(`${API}/renewal/memo${policy}`, {
        headers: authHeaders(),
      });

      const data = await safeJson(res);

      if (res.status === 401 || res.status === 403) {
        clearSession();
        router.replace("/login?expired=1");
        return;
      }

      if (!res.ok) {
        setRenewalMemo(buildLocalMemo());
        setMessage(`Backend memo route returned ${res.status}. LossQ generated a local renewal memo from visible claims.`);
        return;
      }

      const backendMemo =
        data?.memo ||
        data?.renewal_memo ||
        data?.content ||
        data?.summary ||
        "";

      if (!backendMemo || String(backendMemo).toLowerCase().includes("insufficient")) {
        setRenewalMemo(buildLocalMemo());
        setMessage("Backend memo did not return enough account detail. LossQ generated a local renewal memo from visible claims.");
        return;
      }

      setRenewalMemo(
        `Policy analyzed: ${data?.policy_number || selectedPolicy || "Selected Account"}\nClaims used: ${
          data?.claims_used ?? visibleClaims.length
        }\n\n${backendMemo}`
      );
    } catch (error: any) {
      setRenewalMemo(buildLocalMemo());
      setMessage(`Backend memo failed. LossQ generated a local renewal memo from visible claims.`);
    } finally {
      setMemoLoading(false);
    }
  }


  async function generateCarrierPacket() {
    if (!canUseFeature("carrier_packet")) {
      setMessage("Carrier Packet is not included in the current package.");
      return;
    }

    const query = buildReportQuery();

    setMessage("Generating carrier submission packet...");

    try {
      await downloadPdf(
        `${API}/reports/carrier-packet-pdf${query}`,
        "lossq_carrier_submission_packet.pdf",
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify(buildReportPayload()),
        }
      );

      setMessage("Carrier submission packet generated.");
    } catch (error: any) {
      console.error("Carrier packet POST failed:", error);

      try {
        setMessage("Carrier packet POST failed. Trying fallback export...");

        await downloadPdf(
          `${API}/reports/carrier-packet-pdf${query}`,
          "lossq_carrier_submission_packet.pdf",
          {
            method: "GET",
          }
        );

        setMessage("Carrier submission packet generated using fallback export.");
      } catch (fallbackError: any) {
        console.error("Carrier packet fallback failed:", fallbackError);
        setMessage(
          `Carrier packet failed. ${
            fallbackError?.message || error?.message || "Please refresh and try again."
          }`
        );
      }
    }
  }


  async function prepareCarrierEmail() {
    if (!canUseFeature("carrier_email_draft")) {
      setMessage("Prepare Carrier Email is not included in the current package.");
      return;
    }

    const selectedName =
      displayProfile?.business_name ||
      displayProfile?.insured ||
      profile?.business_name ||
      profile?.insured ||
      "Selected Account";

    const selectedPolicy =
      displayProfile?.policy_number ||
      profile?.policy_number ||
      displayProfile?.account_number ||
      safeDisplayProfile?.account_number ||
      displayProfile?.customer_number ||
      safeDisplayProfile?.customer_number ||
      getCachedSelectedPolicy() ||
      "Not Set";

    const packetChoiceRaw =
      window.prompt(
        "Which packet should LossQ prepare?\n\nType one:\ncarrier\nexecutive\nboth",
        "carrier"
      ) || "carrier";

    const packetChoice = packetChoiceRaw.trim().toLowerCase();

    const useCarrier = packetChoice.includes("carrier") || packetChoice.includes("both");
    const useExecutive = packetChoice.includes("executive") || packetChoice.includes("both");

    if (!useCarrier && !useExecutive) {
      setMessage("Carrier email canceled. Choose carrier, executive, or both.");
      return;
    }

    const recipient =
      window.prompt("Enter carrier / underwriter email address. You can leave this blank.", "") || "";

    setMessage("Preparing packet download and carrier email draft...");

    if (useCarrier) {
      await generateCarrierPacket();
    }

    if (useExecutive) {
      await exportExecutiveReport();
    }

    const claimsUsed = visibleClaims.length || claims.length || 0;
    const riskLevel =
      effectiveSummary?.renewal_risk_level ||
      effectiveSummary?.risk_level ||
      localRenewalRiskLevel ||
      "Needs Review";

    const renewalScore =
      effectiveSummary?.renewal_score ??
      localRenewalScore ??
      "Not Rated";

    const incurred = Number(totalIncurred || 0).toLocaleString();
    const reserve = Number(totalReserve || 0).toLocaleString();
    const openCount = Number(openClaims || 0).toLocaleString();

    const packetLabel =
      useCarrier && useExecutive
        ? "LossQ carrier submission packet and executive underwriting report"
        : useExecutive
        ? "LossQ executive underwriting report"
        : "LossQ carrier submission packet";

    const subject = `Renewal Submission - ${selectedName}`;

    const body = [
      `Good afternoon,`,
      ``,
      `Please see the attached ${packetLabel} for review.`,
      ``,
      `Account: ${selectedName}`,
      `Policy / Account Number: ${selectedPolicy}`,
      `Claims Reviewed: ${claimsUsed}`,
      `Open Claims: ${openCount}`,
      `Total Incurred: $${incurred}`,
      `Outstanding Reserve: $${reserve}`,
      `Renewal Score: ${renewalScore}`,
      `Renewal Risk Level: ${riskLevel}`,
      ``,
      `The submission package includes account profile detail, policy schedule, claim summary, renewal risk analysis, carrier appetite, market positioning, premium forecast, and underwriting recommendations generated through LossQ.`,
      ``,
      `Please let me know if you need updated loss runs, claim narratives, exposure detail, driver safety information, loss-control documentation, or any additional underwriting information for quoting consideration.`,
      ``,
      `Thank you,`,
    ].join("\n");

    const mailtoUrl = `mailto:${encodeURIComponent(recipient)}?subject=${encodeURIComponent(
      subject
    )}&body=${encodeURIComponent(body)}`;

    window.location.href = mailtoUrl;

    setMessage("Carrier email draft opened. Attach the downloaded packet before sending.");
  }

  function copyRenewalMemo() {
    navigator.clipboard.writeText(renewalMemo || "");
    setMessage("Renewal memo copied.");
  }



// LOSSQ_COPILOT_ACCOUNT_POLICY_SET_PAYLOAD_V1
function lossqCopilotPolicyNumbersFromProfile(profileLike: any): string[] {
  const values = [
    profileLike?.policy_number,
    profileLike?.account_number,
    profileLike?.customer_number,
    ...(Array.isArray(profileLike?.policies)
      ? profileLike.policies.map((item: any) => item?.policy_number)
      : []),
    ...(Array.isArray(profileLike?.policy_schedule)
      ? profileLike.policy_schedule.map((item: any) => item?.policy_number)
      : []),
  ];

  return Array.from(
    new Set(
      values
        .map((item) => normalizePolicyNumber(item))
        .filter((item) => item && item !== "POLICY NOT SET" && item !== "NOT SET")
    )
  );
}




// LOSSQ_COPILOT_ACCOUNT_POLICY_SET_PAYLOAD_SAFE_V2
function lossqCopilotPolicyNumbersFromProfileSafe(profileLike: any): string[] {
  const values = [
    profileLike?.policy_number,
    profileLike?.account_number,
    profileLike?.customer_number,
    ...(Array.isArray(profileLike?.policies)
      ? profileLike.policies.map((item: any) => item?.policy_number)
      : []),
    ...(Array.isArray(profileLike?.policy_schedule)
      ? profileLike.policy_schedule.map((item: any) => item?.policy_number)
      : []),
  ];

  return Array.from(
    new Set(
      values
        .map((item) => normalizePolicyNumber(item))
        .filter((item) => item && item !== "POLICY NOT SET" && item !== "NOT SET")
    )
  );
}


async function askCopilot(questionOverride?: string) {
    const question = questionOverride || copilotQuestion;

    if (!question.trim()) {
      setCopilotAnswer("Ask a question first.");
      return;
    }

    if (!profile?.policy_number) {
      setCopilotAnswer(
        "Select a policy/account first so Copilot analyzes the correct claims."
      );
      setCopilotOpen(true);
      return;
    }

    setCopilotOpen(true);
    setCopilotLoading(true);
    // LOSSQ_COPILOT_MISSING_VARIABLES_FIX_V1
    const copilotProfile =
      displayProfile ||
      activeProfileRef.current ||
      profile ||
      {};

    const copilotPolicyNumbers = Array.from(
      new Set([
        ...lossqCopilotPolicyNumbersFromProfileSafe(copilotProfile),
        ...lossqCopilotPolicyNumbersFromProfileSafe(activeProfileRef.current),
        ...lossqCopilotPolicyNumbersFromProfileSafe(profile),
        ...(Array.isArray(policySchedule)
          ? policySchedule.map((item: any) => normalizePolicyNumber(item?.policy_number))
          : []),
      ].filter(Boolean))
    );

    const copilotPrimaryPolicy =
      normalizePolicyNumber(copilotProfile?.policy_number) ||
      normalizePolicyNumber(copilotProfile?.account_number) ||
      normalizePolicyNumber(profile?.policy_number) ||
      normalizePolicyNumber(safeDisplayProfile?.account_number) ||
      getCachedSelectedPolicy() ||
      "";

    const copilotVisibleClaims = Array.isArray(claims) ? claims : [];

    setCopilotAnswer(`Thinking about account ${getAccountDisplayName(copilotProfile) || copilotPrimaryPolicy || "selected account"}...`);

    try {
      const res = await fetch(`${API}/copilot/ask`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...authHeaders(),
        },
        body: JSON.stringify({
          question,
          policy_number: copilotPrimaryPolicy,
            account_number: copilotProfile?.account_number || copilotProfile?.customer_number || "",
            profile_id: copilotProfile?.id || profile?.id || null,
            policy_numbers: copilotPolicyNumbers,
            visible_claims: copilotVisibleClaims,
            profile: copilotProfile,
        }),
      });

      const data = await safeJson(res);

      if (res.status === 401 || res.status === 403) {
        clearSession();
        router.replace("/login?expired=1");
        return;
      }

      if (!res.ok) {
        setCopilotAnswer(JSON.stringify(data));
        return;
      }

      setCopilotAnswer(
        `Policy analyzed: ${data?.policy_number || copilotPrimaryPolicy}\nClaims used: ${
          data?.claims_used ?? visibleClaims.length
        }\n\n${data?.answer || "No answer returned."}`
      );
      setCopilotQuestion(question);
    } catch {
      setCopilotAnswer("Copilot failed.");
    } finally {
      setCopilotLoading(false);
    }
  }

  async function openClaimRecord(claim: any) {
    if (!claim) return;

    setSelectedClaimDetail(claim);
    setCachedSelectedClaim(claim);

    const claimNumber =
      claim?.claim_number ||
      claim?.claimNumber ||
      claim?.claim_no ||
      claim?.number ||
      "";

    const policyNumber =
      claim?.policy_number ||
      claim?.policyNumber ||
      claim?.policy_no ||
      profile?.policy_number ||
      "";

    if (claim?.id) {
      router.push(
        `/claims/${claim.id}?claim_number=${encodeURIComponent(
          claimNumber
        )}&policy_number=${encodeURIComponent(policyNumber)}`
      );
      return;
    }

    try {
      setMessage(`Opening claim ${getClaimNumberValue(claim)} detail...`);

      const res = await fetch(`${API}/claims/`, { headers: authHeaders() });
      const data = res.ok ? await safeJson(res) : null;

      const serverClaims = Array.isArray(data)
        ? data
        : Array.isArray(data?.claims)
        ? data.claims
        : [];

      const match = serverClaims.find((item: any) => sameClaimRecord(item, claim));

      if (match?.id) {
        const mergedClaim = {
          ...claim,
          ...match,
        };

        setCachedSelectedClaim(mergedClaim);

        router.push(
          `/claims/${match.id}?claim_number=${encodeURIComponent(
            claimNumber || match?.claim_number || ""
          )}&policy_number=${encodeURIComponent(
            policyNumber || match?.policy_number || ""
          )}`
        );
        return;
      }

      setMessage(
        "Claim detail opened in preview because the saved database claim ID was not returned."
      );
    } catch {
      setMessage("Claim detail opened in preview because claim lookup failed.");
    }
  }

  function logout() {
    clearSession();
    router.replace("/login?fresh=1");
  }

const safeDisplayProfile = {
  ...(profile || {}),
  account_number: lossqCleanAccountNumber(profile?.account_number),
  customer_number: lossqCleanAccountNumber(profile?.customer_number),
};

const backendAccountProfile =
  summary?.account_profile ||
  submissionBuilder?.account_profile ||
  premiumForecast?.account_profile ||
  carrierMatch?.account_profile ||
  carrierAppetite?.account_profile ||
  decision?.account_profile ||
  {};

const backendPolicyNumbers = [
  ...(Array.isArray(summary?.policy_numbers_used) ? summary.policy_numbers_used : []),
  ...(Array.isArray(submissionBuilder?.policy_numbers_used)
    ? submissionBuilder.policy_numbers_used
    : []),
  ...(Array.isArray(premiumForecast?.policy_numbers_used)
    ? premiumForecast.policy_numbers_used
    : []),
  ...(Array.isArray(carrierMatch?.policy_numbers_used) ? carrierMatch.policy_numbers_used : []),
  ...(Array.isArray(carrierAppetite?.policy_numbers_used)
    ? carrierAppetite.policy_numbers_used
    : []),
  ...(Array.isArray(decision?.policy_numbers_used) ? decision.policy_numbers_used : []),
];

/*
  Guardrail: backendPolicyNumbers are useful for intelligence widgets, but they must
  NOT drive the Claims tab filter. Some backend endpoints can return stale policy
  numbers from the previously selected account when a newly uploaded file saved
  zero claims. Claims filtering must rely only on the selected profile/account and
  the selected profile's own policy schedule.
*/

const recoveredPolicySchedule = firstNonEmptyArray(
  (activeProfileRef.current?.policies?.length || 0) > 0 ? activeProfileRef.current.policies : null,
  profile?.policies,
  backendAccountProfile?.policies,
  summary?.account_profile?.policies,
  submissionBuilder?.account_profile?.policies
);

const displayProfile = {
  ...(backendAccountProfile || {}),
  ...(profile || {}),
  policies: recoveredPolicySchedule,
};

const claimBasedPolicySchedule = Object.values(
  (claims || []).reduce((acc: any, claim: any) => {
    const line =
      claim?.line_of_business ||
      claim?.lob ||
      claim?.coverage_line ||
      claim?.coverage ||
      claim?.claim_type ||
      "Other Commercial Line";

    const key = String(line || "Other Commercial Line").trim();

    if (!acc[key]) {
      acc[key] = {
        policy_type: key,
        line_of_business: key,
        coverage: key,
        policy_number:
          claim?.policy_number ||
          displayProfile?.policy_number ||
          displayProfile?.account_number ||
          "",
        writing_carrier:
          claim?.writing_carrier ||
          claim?.carrier_name ||
          displayProfile?.writing_carrier ||
          displayProfile?.carrier_name ||
          "",
        carrier:
          claim?.carrier ||
          claim?.carrier_name ||
          displayProfile?.carrier_name ||
          "",
        effective_date: displayProfile?.effective_date || "",
        expiration_date: displayProfile?.expiration_date || "",
        claim_count: 0,
        total_incurred: 0,
      };
    }

    acc[key].claim_count += 1;
    acc[key].total_incurred += Number(
      claim?.total_incurred ||
      claim?.incurred ||
      claim?.total ||
      0
    );

    return acc;
  }, {})
);

const policySchedule =
  blankWorkspaceMode
    ? []
    : recoveredPolicySchedule.length > 0
    ? recoveredPolicySchedule
    : claimBasedPolicySchedule;

// LOSSQ_AUTO_FILL_EXPOSURE_INPUTS_EFFECT_AFTER_PROFILE_READY_V1
useEffect(() => {
  if (blankWorkspaceMode) return;

  const hasAccount =
    Boolean(displayProfile?.business_name) ||
    Boolean(displayProfile?.insured) ||
    Boolean(displayProfile?.policy_number) ||
    Boolean(displayProfile?.account_number) ||
    (Array.isArray(policySchedule) && policySchedule.length > 0);

  if (!hasAccount) return;

  // LOSSQ_EXPOSURE_AUTOFILL_CLICK_ONLY_V1
  // Do not auto-run exposure auto-fill when the Exposure Inputs page loads.
  // Auto-Fill should only run when the user clicks the button.
}, [
  blankWorkspaceMode,
  displayProfile?.business_name,
  displayProfile?.insured,
  displayProfile?.policy_number,
  displayProfile?.account_number,
  displayProfile?.current_premium,
  displayProfile?.expiring_premium,
  displayProfile?.target_renewal_premium,
  Array.isArray(policySchedule) ? policySchedule.length : 0,
]);




// LOSSQ_FINAL_BAD_POLICY_DISPLAY_GUARDRAIL
const safeDisplayAccountKey = chooseSafePolicyNumber(
  displayProfile?.account_number,
  displayProfile?.customer_number,
  safeDisplayProfile?.account_number,
  safeDisplayProfile?.customer_number,
  displayProfile?.policy_number,
  profile?.policy_number
);

if (isBadPolicyNumberValue(displayProfile?.policy_number) && safeDisplayAccountKey) {
  displayProfile.policy_number = safeDisplayAccountKey;
}

if (isBadPolicyNumberValue(profile?.policy_number) && safeDisplayAccountKey) {
  profile.policy_number = safeDisplayAccountKey;
}


const mainPolicyNumber = blankWorkspaceMode
  ? ""
  : chooseSafePolicyNumber(
  ...(policySchedule || []).map((item: any) => item?.policy_number),
  ...(Array.isArray(displayProfile?.policies) ? displayProfile.policies.map((item: any) => item?.policy_number) : []),
  ...(Array.isArray(profile?.policies) ? profile.policies.map((item: any) => item?.policy_number) : []),
  ...(claims || []).map((claim: any) => claim?.policy_number || claim?.policyNumber || claim?.policy_no)
);

const activeAccountPolicyNumber = normalizePolicyNumber(displayProfile?.policy_number);
const activeAccountNumber = normalizePolicyNumber(displayProfile?.account_number);
const activeCustomerNumber = normalizePolicyNumber(displayProfile?.customer_number);

const activePolicyNumbers = blankWorkspaceMode
  ? []
  : Array.from(
  new Set(
    [
      ...policySchedule.map((item: any) => item?.policy_number),
      activeAccountPolicyNumber,
      activeAccountNumber,
      activeCustomerNumber,
    ]
      .map((item: any) => normalizePolicyNumber(item))
      .filter(Boolean)
  )
);

const hasActiveAccount = Boolean(
  getAccountDisplayName(displayProfile) ||
    displayProfile?.carrier_name ||
    displayProfile?.policy_number ||
    activePolicyNumbers.length > 0 ||
    summary?.claims_used != null
);
const filteredVisibleClaims = claims;

const currentUploadReview = getCachedCurrentUpload();
const currentUploadClaims = Array.isArray(currentUploadReview?.claims)
  ? currentUploadReview.claims
  : [];
const currentUploadPolicySet = new Set(
  [
    currentUploadReview?.profile?.policy_number,
    currentUploadReview?.safeDisplayProfile?.account_number,
    ...(Array.isArray(currentUploadReview?.policy_numbers)
      ? currentUploadReview.policy_numbers
      : []),
    ...(Array.isArray(currentUploadReview?.policies)
      ? currentUploadReview.policies.map((item: any) => item?.policy_number)
      : []),
  ]
    .map((item: any) => normalizePolicyNumber(item))
    .filter(Boolean)
);
const currentUploadMatches = currentUploadClaims.filter((claim: any) => {
  const claimPolicy = getClaimPolicyNumber(claim);

  if (activePolicyNumbers.length > 0) {
    return activePolicyNumbers.includes(claimPolicy);
  }

  if (currentUploadPolicySet.size > 0) {
    return currentUploadPolicySet.has(claimPolicy);
  }

  return false;
});

const lastUploadReview = getCachedLastUploadReview();
const lastUploadClaims = Array.isArray(lastUploadReview?.claims)
  ? lastUploadReview.claims
  : [];
const lastUploadPolicySet = new Set(
  [
    lastUploadReview?.profile?.policy_number,
    lastUploadReview?.safeDisplayProfile?.account_number,
    ...(Array.isArray(lastUploadReview?.policies)
      ? lastUploadReview.policies.map((item: any) => item?.policy_number)
      : []),
  ]
    .map((item: any) => normalizePolicyNumber(item))
    .filter(Boolean)
);


// LOSSQ_HAS_VALIDATED_CLAIM_DATA_HELPER_V1
function hasValidatedClaimData(claim: any) {
  if (!claim || typeof claim !== "object") return false;

  const claimNumber = String(
    claim.claim_number ||
    claim.claimNumber ||
    claim.number ||
    ""
  ).trim();

  const policyNumber = String(
    claim.policy_number ||
    claim.policyNumber ||
    claim.policy_no ||
    claim.policyNo ||
    ""
  ).trim();

  const totalIncurred = Number(
    claim.total_incurred ??
    claim.totalIncurred ??
    claim.incurred ??
    0
  );

  const paidAmount = Number(
    claim.paid_amount ??
    claim.paidAmount ??
    claim.paid ??
    0
  );

  const reserveAmount = Number(
    claim.reserve_amount ??
    claim.reserveAmount ??
    claim.reserve ??
    0
  );

  return Boolean(
    claimNumber ||
    policyNumber ||
    totalIncurred > 0 ||
    paidAmount > 0 ||
    reserveAmount > 0
  );
}

// LOSSQ_VISIBLE_CLAIMS_BACKEND_ONLY_V1
// Claims Analysis must display backend /claims rows only.
// Do not fall back to current upload or last upload cache because those can carry stale policy/line values.
const visibleClaims = blankWorkspaceMode ? [] : filteredVisibleClaims;

const validatedVisibleClaims = visibleClaims.filter((claim: any) => hasValidatedClaimData(claim));
const intelligenceClaims = validatedVisibleClaims.length > 0 ? validatedVisibleClaims : visibleClaims;
const validatedClaimsAvailable = intelligenceClaims.length > 0;

const backendMetrics =
  summary?.renewal_metrics ||
  summary?.metrics ||
  decision?.decision_metrics ||
  carrierAppetite?.appetite_metrics ||
  premiumForecast?.forecast_metrics ||
  submissionBuilder?.supporting_intelligence?.summary?.renewal_metrics ||
  submissionBuilder?.supporting_intelligence?.summary?.metrics ||
  {};

const backendClaimsUsed =
  summary?.claims_used ??
  submissionBuilder?.claims_used ??
  premiumForecast?.claims_used ??
  carrierMatch?.claims_used ??
  carrierAppetite?.claims_used ??
  decision?.claims_used;

const totalClaims = hasActiveAccount
  ? visibleClaims.length
  : Number(backendMetrics?.total_claims ?? backendClaimsUsed ?? 0);

const openClaims = hasActiveAccount
  ? visibleClaims.filter((c: any) => String(c.status || "").toLowerCase() === "open").length
  : Number(backendMetrics?.open_claims ?? 0);

const totalIncurred = hasActiveAccount
  ? visibleClaims.reduce((sum: number, c: any) => sum + getClaimIncurred(c), 0)
  : Number(backendMetrics?.total_incurred ?? 0);

const openVisibleClaims = visibleClaims.filter((claim: any) => isOpenClaimStatus(claim));
const closedVisibleClaims = visibleClaims.filter((claim: any) => !isOpenClaimStatus(claim));
const groupedVisibleClaims = [...openVisibleClaims, ...closedVisibleClaims];

const localClaimTotal = intelligenceClaims.reduce((sum: number, c: any) => sum + getClaimIncurred(c), 0);
const localOpenClaimCount = intelligenceClaims.filter((claim: any) => isOpenClaimStatus(claim)).length;
const localLitigationCount = intelligenceClaims.filter((c: any) => {
  const text = `${c?.litigation || ""} ${c?.litigation_status || ""} ${c?.description || ""} ${c?.flag || ""}`.toLowerCase();
  return text.includes("litigation") || text.includes("attorney") || text.includes("suit");
}).length;
const localLargeLossCount = intelligenceClaims.filter((c: any) => getClaimIncurred(c) >= 50000).length;
const localRenewalPenalty = Math.min(70, localOpenClaimCount * 10 + localLitigationCount * 15 + localLargeLossCount * 10 + Math.max(0, intelligenceClaims.length - 3) * 4);
const localRenewalScore = intelligenceClaims.length > 0 ? Math.max(30, 92 - localRenewalPenalty) : null;
const localRenewalRiskLevel =
  localRenewalScore == null
    ? "Insufficient Data"
    : localRenewalScore >= 80
    ? "Low"
    : localRenewalScore >= 65
    ? "Moderate"
    : localRenewalScore >= 50
    ? "High"
    : "Critical";
const localCarrierAppetiteScore = localRenewalScore == null ? null : Math.max(20, Math.min(95, localRenewalScore - localLargeLossCount * 4));
const localSubmissionReadinessScore = intelligenceClaims.length > 0 ? Math.min(95, 70 + Math.min(20, visibleClaims.length * 3)) : null;

const backendInsufficientText = JSON.stringify({ summary, decision, carrierAppetite, submissionReadiness, premiumForecast, carrierMatch }).toLowerCase();
const backendSaysInsufficient =
  backendInsufficientText.includes("insufficient") ||
  backendInsufficientText.includes("no account-specific claims") ||
  backendInsufficientText.includes("no account specific claims") ||
  backendInsufficientText.includes("no validated claims") ||
  backendInsufficientText.includes("not parsed or validated") ||
  backendInsufficientText.includes("claims were not parsed") ||
  backendInsufficientText.includes("no carrier match generated") ||
  Number(backendClaimsUsed || 0) === 0;

const localRenewalDrivers = [
  `${intelligenceClaims.length} claim(s) analyzed for the selected account.`,
  `${localOpenClaimCount} open claim(s).`,
  `$${Number(localClaimTotal || 0).toLocaleString()} total incurred.`,
  `${localLargeLossCount} large loss claim(s) at or above $50,000.`,
  `${localLitigationCount} litigation/attorney indicator(s).`,
];

const effectiveSummary = summary;
const effectiveDecision = decision;

// Local claim lines remain available only for display helpers, charts, and claim detail views.
// They are no longer used to manufacture Renewal Risk or Underwriter Decision scores.
const localClaimLines = Array.from(
  new Set(
    intelligenceClaims
      .map((claim: any) =>
        String(
          claim?.line_of_business ||
            claim?.lineOfBusiness ||
            claim?.claim_type ||
            claim?.claimType ||
            claim?.coverage ||
            ""
        ).toLowerCase()
      )
      .filter(Boolean)
  )
);

const appetiteHasAuto = localClaimLines.some(
  (line) => line.includes("auto") || line.includes("truck")
);
const appetiteHasGL = localClaimLines.some(
  (line) => line.includes("general") || line.includes("liability")
);
const appetiteHasWC = localClaimLines.some(
  (line) => line.includes("worker") || line.includes("comp")
);
const appetiteHasCargo = localClaimLines.some((line) => line.includes("cargo"));

const appetiteOpenClaimsCount = intelligenceClaims.filter((claim: any) =>
  isOpenClaimStatus(claim)
).length;

const appetiteTotalReserve = intelligenceClaims.reduce((sum: number, claim: any) => {
  return (
    sum +
    toMoneyNumber(
      claim?.reserve_amount ||
        claim?.reserveAmount ||
        claim?.reserve ||
        claim?.outstanding_reserve ||
        0
    )
  );
}, 0);

const appetiteHasLargeLoss = intelligenceClaims.some(
  (claim: any) => getClaimIncurred(claim) >= 50000
);

const appetiteHasOpenReserveConcern =
  appetiteOpenClaimsCount > 0 && appetiteTotalReserve > 25000;

const localCarrierBuckets = [];

if (appetiteHasAuto) {
  localCarrierBuckets.push({
    carrier_type: appetiteHasOpenReserveConcern
      ? "Transportation / Commercial Auto Selective Market"
      : "Transportation-Focused Standard Auto Market",
    match_score: Math.max(
      35,
      Math.min(92, (localCarrierAppetiteScore || 60) + (appetiteHasOpenReserveConcern ? -8 : 6))
    ),
    fit: appetiteHasOpenReserveConcern ? "Conditional fit" : "Strong fit",
  });
}

if (appetiteHasGL) {
  localCarrierBuckets.push({
    carrier_type: appetiteHasLargeLoss
      ? "Regional Casualty / General Liability Selective Market"
      : "Regional General Liability Market",
    match_score: Math.max(
      35,
      Math.min(90, (localCarrierAppetiteScore || 60) + (appetiteHasLargeLoss ? -5 : 4))
    ),
    fit: appetiteHasLargeLoss ? "Moderate fit with narrative" : "Moderate fit",
  });
}

if (appetiteHasWC) {
  localCarrierBuckets.push({
    carrier_type:
      appetiteOpenClaimsCount > 0
        ? "Workers Comp Loss-Sensitive Market"
        : "Workers Comp Standard Market",
    match_score: Math.max(
      35,
      Math.min(88, (localCarrierAppetiteScore || 60) - (appetiteOpenClaimsCount > 0 ? 6 : 0))
    ),
    fit: appetiteOpenClaimsCount > 0 ? "Conditional fit" : "Standard fit",
  });
}

if (appetiteHasCargo) {
  localCarrierBuckets.push({
    carrier_type: "Motor Truck Cargo Market",
    match_score: Math.max(40, Math.min(90, (localCarrierAppetiteScore || 60) + 3)),
    fit: "Line-specific fit",
  });
}

if (localCarrierBuckets.length === 0) {
  localCarrierBuckets.push({
    carrier_type: "Commercial Casualty Market",
    match_score: localCarrierAppetiteScore || 60,
    fit: "Needs coverage classification",
  });
}

const effectiveCarrierAppetite = carrierAppetite;


// LOSSQ_EXPOSURE_PREMIUM_FORECAST_LINK_V1
// LOSSQ_FORCE_FILE_EXPOSURE_PREMIUM_FORECAST_V1
function parsePremiumInput(value: any): number {
  if (value === null || value === undefined) return 0;

  if (typeof value === "number") {
    return Number.isFinite(value) ? value : 0;
  }

  const cleaned = String(value)
    .replace(/[$,]/g, "")
    .replace(/[^0-9.-]/g, "")
    .trim();

  const parsed = Number(cleaned);
  return Number.isFinite(parsed) ? parsed : 0;
}

function isInsufficientBackendMessage(value: any) {
  const text = String(value || "").toLowerCase();

  return (
    !text ||
    text.includes("insufficient") ||
    text.includes("no validated claims") ||
    text.includes("no carrier match generated") ||
    text.includes("claims were not parsed") ||
    text.includes("not parsed or validated") ||
    text.includes("claims were not validated") ||
    text.includes("no account-specific claims") ||
    text.includes("no account specific claims") ||
    text.includes("no forecast generated")
  );
}

// LOSSQ_EXPOSURE_FORECAST_OVERRIDE_PRIORITY_V1
const profileCurrentPremium =
  parsePremiumInput(profile?.current_premium) ||
  parsePremiumInput(displayProfile?.current_premium) ||
  parsePremiumInput(profile?.expiring_premium) ||
  parsePremiumInput(displayProfile?.expiring_premium);

const manualTargetRenewalPremium =
  parsePremiumInput(profile?.target_renewal_premium) ||
  parsePremiumInput(displayProfile?.target_renewal_premium);

const exposureInputsHavePremiumOverride =
  profileCurrentPremium > 0 || manualTargetRenewalPremium > 0;

const hasRealCurrentPremium =
  profileCurrentPremium > 0 ||
  parsePremiumInput(premiumForecast?.current_premium) > 0 ||
  parsePremiumInput(premiumForecast?.currentPremium) > 0;

const realCurrentPremium =
  profileCurrentPremium ||
  parsePremiumInput(premiumForecast?.current_premium) ||
  parsePremiumInput(premiumForecast?.currentPremium) ||
  0;

const manualTargetIncreasePercent =
  manualTargetRenewalPremium > 0 && realCurrentPremium > 0
    ? Math.round(((manualTargetRenewalPremium - realCurrentPremium) / realCurrentPremium) * 100)
    : null;

const localPremiumIncreasePercent =
  manualTargetIncreasePercent != null
    ? manualTargetIncreasePercent
    : intelligenceClaims.length > 0
    ? localRenewalRiskLevel === "Low"
      ? 5
      : localRenewalRiskLevel === "Moderate"
      ? 12
      : localRenewalRiskLevel === "High"
      ? 25
      : 40
    : null;

const localPremiumConfidence =
  intelligenceClaims.length > 0
    ? Math.min(85, 55 + Math.min(30, intelligenceClaims.length * 5))
    : null;

const localPremiumBestCase =
  localPremiumIncreasePercent != null
    ? Math.max(0, localPremiumIncreasePercent - 8)
    : null;

const localPremiumWorstCase =
  localPremiumIncreasePercent != null
    ? localPremiumIncreasePercent + 18
    : null;

const localExpectedRenewalPremium =
  manualTargetRenewalPremium > 0
    ? manualTargetRenewalPremium
    : hasRealCurrentPremium && localPremiumIncreasePercent != null
    ? Math.round(realCurrentPremium * (1 + localPremiumIncreasePercent / 100))
    : null;

const premiumBackendHasUsableForecast =
  !exposureInputsHavePremiumOverride &&
  parsePremiumInput(premiumForecast?.current_premium) > 0 &&
  parsePremiumInput(premiumForecast?.expected_renewal_premium) > 0 &&
  !isInsufficientBackendMessage(premiumForecast?.forecast_summary);

const localForecastDrivers =
  intelligenceClaims.length > 0
    ? [
        `${intelligenceClaims.length} validated claim row(s) loaded for the selected account.`,
        `${localOpenClaimCount} open claim(s) affecting renewal pressure.`,
        `$${Number(localClaimTotal || 0).toLocaleString()} total incurred losses.`,
        `${localLargeLossCount} large loss claim(s) at or above $50,000.`,
        `${localLitigationCount} litigation/attorney indicator(s).`,
        manualTargetRenewalPremium > 0
          ? `Manual target renewal premium of $${Number(manualTargetRenewalPremium || 0).toLocaleString()} was used as the renewal premium override.`
          : hasRealCurrentPremium
          ? `Current premium of $${Number(realCurrentPremium || 0).toLocaleString()} was used to estimate renewal premium.`
          : "Current premium/exposure data is missing, so LossQ is showing a claim-based pressure estimate instead of a renewal dollar projection.",
      ]
    : ["No validated claims were available."];

// LOSSQ_PREMIUM_FORECAST_USE_EXPOSURE_DERIVED_FILE_DATA_V1
const profileDerivedExposure = deriveExposureInputsFromPolicyRows(profile);
const displayDerivedExposure = deriveExposureInputsFromPolicyRows(displayProfile);
const fileExposureCurrentPremium =
  parsePremiumInput(profile?.current_premium) ||
  parsePremiumInput(displayProfile?.current_premium) ||
  parsePremiumInput(profileDerivedExposure?.current_premium) ||
  parsePremiumInput(displayDerivedExposure?.current_premium) ||
  parsePremiumInput(profile?.expiring_premium) ||
  parsePremiumInput(displayProfile?.expiring_premium) ||
  parsePremiumInput(profileDerivedExposure?.expiring_premium) ||
  parsePremiumInput(displayDerivedExposure?.expiring_premium);

const fileExposureTargetRenewalPremium =
  parsePremiumInput(profile?.target_renewal_premium) ||
  parsePremiumInput(displayProfile?.target_renewal_premium) ||
  parsePremiumInput(profileDerivedExposure?.target_renewal_premium) ||
  parsePremiumInput(displayDerivedExposure?.target_renewal_premium) ||
  parsePremiumInput(displayDerivedExposure?.target_renewal_premium);

const fileExposureHasPremiumData = fileExposureCurrentPremium > 0;

const fileExposureIncreasePercent =
  fileExposureTargetRenewalPremium > 0 && fileExposureCurrentPremium > 0
    ? Math.round(
        ((fileExposureTargetRenewalPremium - fileExposureCurrentPremium) /
          fileExposureCurrentPremium) *
          100
      )
    : localPremiumIncreasePercent;

const fileExposureExpectedRenewalPremium =
  fileExposureTargetRenewalPremium > 0
    ? fileExposureTargetRenewalPremium
    : fileExposureCurrentPremium > 0 && fileExposureIncreasePercent != null
    ? Math.round(fileExposureCurrentPremium * (1 + fileExposureIncreasePercent / 100))
    : null;

const effectivePremiumForecast =
  fileExposureHasPremiumData
    ? {
        forecast_type: "premium_projection",
        data_source: "saved_file_exposure_inputs",
        current_premium: fileExposureCurrentPremium,
        expected_renewal_premium: fileExposureExpectedRenewalPremium || 0,
        expected_increase_percent: fileExposureIncreasePercent,
        confidence_score: localPremiumConfidence || 80,
        best_case_percent:
          fileExposureIncreasePercent != null
            ? Math.max(0, fileExposureIncreasePercent - 5)
            : null,
        likely_range_percent:
          fileExposureIncreasePercent != null
            ? `${Math.max(0, fileExposureIncreasePercent - 5)}% to ${
                fileExposureIncreasePercent + 10
              }%`
            : "-",
        worst_case_percent:
          fileExposureIncreasePercent != null
            ? fileExposureIncreasePercent + 10
            : null,
        forecast_drivers: [
          "Premium Forecast is using actual Exposure Inputs from the uploaded account file, not stale modeled backend premium.",
          `Current premium from Exposure Inputs: $${Number(
            fileExposureCurrentPremium || 0
          ).toLocaleString()}.`,
          fileExposureTargetRenewalPremium > 0
            ? `Target renewal premium override from Exposure Inputs: $${Number(
                fileExposureTargetRenewalPremium || 0
              ).toLocaleString()}.`
            : `Expected renewal premium was calculated from current premium and claim-based renewal pressure.`,
          `${intelligenceClaims.length} account-specific claim row(s) are included in the renewal pressure review.`,
          `$${Number(localClaimTotal || 0).toLocaleString()} total incurred losses from the uploaded account data.`,
        ],
        forecast_summary:
          fileExposureTargetRenewalPremium > 0
            ? `LossQ used the actual saved Exposure Inputs from the account file. Current premium is $${Number(
                fileExposureCurrentPremium || 0
              ).toLocaleString()} and target renewal premium is $${Number(
                fileExposureTargetRenewalPremium || 0
              ).toLocaleString()}, creating an estimated ${
                fileExposureIncreasePercent ?? 0
              }% renewal change.`
            : `LossQ used the actual saved Exposure Inputs from the account file. Current premium is $${Number(
                fileExposureCurrentPremium || 0
              ).toLocaleString()} and expected renewal premium is $${Number(
                fileExposureExpectedRenewalPremium || 0
              ).toLocaleString()} based on the uploaded account claim activity and exposure basis.`,
        claims_used: intelligenceClaims.length,
        policy_numbers_used:
          activePolicyNumbers.length > 0
            ? activePolicyNumbers
            : Array.from(currentUploadPolicySet),
      }
    : validatedClaimsAvailable
    ? {
        ...(premiumForecast || {}),
        forecast_type: "claim_based_pressure_estimate",
        current_premium: null,
        expected_renewal_premium: null,
        expected_increase_percent: localPremiumIncreasePercent,
        confidence_score: localPremiumConfidence,
        best_case_percent: localPremiumBestCase,
        likely_range_percent:
          localPremiumIncreasePercent != null
            ? `${Math.max(0, localPremiumIncreasePercent - 5)}% to ${
                localPremiumIncreasePercent + 10
              }%`
            : "-",
        worst_case_percent: localPremiumWorstCase,
        forecast_drivers: localForecastDrivers,
        forecast_summary: `LossQ has validated claim rows for this account, but no current premium or exposure basis was provided. No renewal dollar amount is being projected. The displayed ${
          localPremiumIncreasePercent ?? 0
        }% is a claims-derived renewal pressure estimate based on claim frequency, severity, open claims, litigation indicators, and total incurred losses.`,
        claims_used: intelligenceClaims.length,
        policy_numbers_used:
          activePolicyNumbers.length > 0
            ? activePolicyNumbers
            : Array.from(currentUploadPolicySet),
        data_source: "backend_engine_only",
      }
    : premiumForecast;


const premiumAccuracyStatus = (() => {
  const currentPremium = Number(effectivePremiumForecast?.current_premium || 0);
  const expectedRenewal = Number(effectivePremiumForecast?.expected_renewal_premium || 0);

  const hasUniversalExposureBasis = Boolean(
    displayProfile?.payroll ||
      displayProfile?.revenue ||
      displayProfile?.sales ||
      displayProfile?.receipts ||
      displayProfile?.employee_count ||
      displayProfile?.employeeCount ||
      displayProfile?.vehicle_count ||
      displayProfile?.vehicleCount ||
      displayProfile?.driver_count ||
      displayProfile?.driverCount ||
      displayProfile?.property_tiv ||
      displayProfile?.tiv ||
      displayProfile?.building_value ||
      displayProfile?.contents_value ||
      displayProfile?.square_footage ||
      displayProfile?.location_count ||
      displayProfile?.unit_count ||
      displayProfile?.class_code ||
      displayProfile?.class_codes ||
      displayProfile?.limits ||
      displayProfile?.deductible ||
      displayProfile?.retention ||
      displayProfile?.experience_mod ||
      displayProfile?.mod ||
      displayProfile?.coverage_limit ||
      displayProfile?.cyber_revenue ||
      displayProfile?.professional_revenue ||
      displayProfile?.cargo_limit ||
      displayProfile?.umbrella_limit ||
      displayProfile?.exposure_basis
  );

  const detectedLines = Array.from(
    new Set(
      [
        ...policySchedule.map((item: any) =>
          String(
            item?.policy_type ||
              item?.line_coverage ||
              item?.line_of_business ||
              item?.coverage ||
              ""
          ).trim()
        ),
        ...intelligenceClaims.map((claim: any) =>
          String(
            claim?.line_of_business ||
              claim?.lob ||
              claim?.coverage_line ||
              claim?.coverage ||
              claim?.claim_type ||
              ""
          ).trim()
        ),
      ].filter(Boolean)
    )
  );

  const lineText =
    detectedLines.length > 0
      ? detectedLines.slice(0, 6).join(", ")
      : "commercial lines of business";

  if (!currentPremium || currentPremium <= 0) {
    return {
      level: "Premium Projection Unavailable",
      confidence: "Insufficient",
      message:
        `Add current premium and exposure basis before relying on a renewal dollar projection. LossQ can still show claim-based renewal pressure across ${lineText}.`,
      allowDollarProjection: false,
    };
  }

  if (!hasUniversalExposureBasis) {
    return {
      level: "Limited Confidence Projection",
      confidence: "Limited",
      message:
        "Current premium is available, but exposure data is missing. Add the exposure basis for the applicable line of business, such as payroll, revenue, sales, class codes, property values, TIV, limits, deductibles, retention, vehicle/unit counts, employee count, or location data.",
      allowDollarProjection: true,
    };
  }

  if (validatedClaimsAvailable && expectedRenewal > 0) {
    return {
      level: "High Confidence Estimate",
      confidence: "Strong",
      message:
        `LossQ has current premium, claim activity, and exposure basis for ${lineText}. This is a defensible renewal premium range, not a guaranteed carrier quote.`,
      allowDollarProjection: true,
    };
  }

  return {
    level: "Moderate Confidence Estimate",
    confidence: "Moderate",
    message:
      "LossQ has partial premium and exposure data. Confirm claim totals, exposure changes, limits, deductibles, retention, class codes, coverage terms, and carrier appetite before final pricing.",
    allowDollarProjection: true,
  };
})();

const backendTopCarriersAreUsable =
  Array.isArray(carrierMatch?.top_carriers) &&
  carrierMatch.top_carriers.length > 0 &&
  !carrierMatch.top_carriers.some((item: any) =>
    isInsufficientBackendMessage(
      `${item?.carrier || ""} ${item?.reason || ""} ${item?.fit || ""} ${item?.summary || ""}`
    )
  );

const realCarrierDatabaseAvailable = Boolean(
  carrierMatch?.carrier_database_enabled ||
    carrierMatch?.real_carrier_database_enabled ||
    carrierMatch?.source === "carrier_database" ||
    carrierMatch?.data_source === "carrier_database"
);

const lineBasedMarketCategories = [];

if (appetiteHasAuto) {
  lineBasedMarketCategories.push({
    market_category: appetiteHasOpenReserveConcern
      ? "Transportation selective market"
      : "Transportation standard market",
    match_score: Math.max(
      35,
      Math.min(92, (localCarrierAppetiteScore || 60) + (appetiteHasOpenReserveConcern ? -8 : 6))
    ),
    fit: appetiteHasOpenReserveConcern
      ? "Conditional market category"
      : "Strong market category",
    reason: appetiteHasOpenReserveConcern
      ? "Auto liability is present with open reserve pressure. Underwriters will need reserve notes, claim status, driver controls, and corrective actions."
      : "Auto liability claims are present, but current visible reserve pressure appears manageable.",
  });
}

if (appetiteHasGL) {
  lineBasedMarketCategories.push({
    market_category: appetiteHasLargeLoss
      ? "Regional casualty selective market"
      : "Regional general liability market",
    match_score: Math.max(
      35,
      Math.min(90, (localCarrierAppetiteScore || 60) + (appetiteHasLargeLoss ? -5 : 4))
    ),
    fit: appetiteHasLargeLoss
      ? "Moderate market category with narrative"
      : "Moderate market category",
    reason: appetiteHasLargeLoss
      ? "General liability or casualty severity may require a detailed loss narrative before standard-market placement."
      : "General liability exposure appears marketable through regional casualty channels based on visible claims.",
  });
}

if (appetiteHasWC) {
  lineBasedMarketCategories.push({
    market_category:
      appetiteOpenClaimsCount > 0
        ? "Workers comp loss-sensitive market"
        : "Workers comp standard market",
    match_score: Math.max(
      35,
      Math.min(88, (localCarrierAppetiteScore || 60) - (appetiteOpenClaimsCount > 0 ? 6 : 0))
    ),
    fit: appetiteOpenClaimsCount > 0
      ? "Conditional market category"
      : "Standard market category",
    reason: appetiteOpenClaimsCount > 0
      ? "Open claim activity may require loss-sensitive underwriting review."
      : "Workers comp exposure can be reviewed in standard channels if payroll/exposure data supports it.",
  });
}

if (appetiteHasCargo) {
  lineBasedMarketCategories.push({
    market_category: "Motor truck cargo market",
    match_score: Math.max(40, Math.min(90, (localCarrierAppetiteScore || 60) + 3)),
    fit: "Line-specific market category",
    reason: "Cargo exposure should be reviewed separately using cargo losses, limits, radius, commodities, and theft controls.",
  });
}

if (lineBasedMarketCategories.length === 0) {
  lineBasedMarketCategories.push({
    market_category: "Needs coverage classification",
    match_score: localCarrierAppetiteScore || 0,
    fit: "Not enough line-of-business data",
    reason: "LossQ needs validated policy line or coverage data before recommending a market category.",
  });
}

const sortedMarketCategories = lineBasedMarketCategories.sort(
  (a, b) => Number(b.match_score || 0) - Number(a.match_score || 0)
);

const effectiveCarrierMatch = carrierMatch;


const effectiveSubmissionReadiness = submissionReadiness;

const scheduleClaimStats = visibleClaims.reduce((acc: AnyObject, claim: any) => {
  const claimPolicy = getClaimPolicyNumber(claim);
  if (!claimPolicy) return acc;

  if (!acc[claimPolicy]) {
    acc[claimPolicy] = { count: 0, totalIncurred: 0 };
  }

  acc[claimPolicy].count += 1;
  acc[claimPolicy].totalIncurred += getClaimIncurred(claim);

  return acc;
}, {});

const flaggedClaims = hasActiveAccount
  ? visibleClaims.filter((c: any) => c.flag).length
  : Number(backendMetrics?.flagged_claims ?? 0);

const totalClaimsDisplay = hasActiveAccount ? totalClaims : "-";
const openClaimsDisplay = hasActiveAccount ? openClaims : "-";
const totalIncurredDisplay = hasActiveAccount
  ? `$${Number(totalIncurred || 0).toLocaleString()}`
  : "-";
const flaggedClaimsDisplay = hasActiveAccount ? flaggedClaims : "-";

const totalReserve = hasActiveAccount
  ? visibleClaims.reduce(
      (sum: number, c: any) =>
        sum + toMoneyNumber(c?.reserve_amount ?? c?.reserve ?? c?.outstanding_reserve),
      0
    )
  : Number(backendMetrics?.total_reserve ?? timeline?.total_reserve ?? 0);

const closedClaims = hasActiveAccount
  ? visibleClaims.filter((c: any) => String(c.status || "").toLowerCase() === "closed").length
  : Number(backendMetrics?.closed_claims ?? Math.max(totalClaims - openClaims, 0));

const litigationClaims = hasActiveAccount
  ? visibleClaims.filter((c: any) => {
      const text = `${c?.litigation || ""} ${c?.claim_status || ""} ${c?.description || ""}`.toLowerCase();
      return text.includes("litigation") || text.includes("litigated") || text.includes("attorney");
    }).length
  : Number(backendMetrics?.litigation_claims ?? 0);

function chartHasData(rows: any[]) {
  return Array.isArray(rows) && rows.some((item) => Number(item?.value || 0) > 0);
}

function buildVisibleClaimYearlyData() {
  const grouped: Record<string, number> = {};

  visibleClaims.forEach((claim: any) => {
    const rawDate = claim?.loss_date || claim?.date_of_loss || claim?.claim_date || "Unknown";
    const yearMatch = String(rawDate).match(/(20\d{2}|19\d{2})/);
    const year = yearMatch?.[1] || "Unknown";
    grouped[year] = (grouped[year] || 0) + getClaimIncurred(claim);
  });

  return objectToChartData(grouped);
}

function buildVisibleClaimLineData() {
  const grouped: Record<string, number> = {};

  visibleClaims.forEach((claim: any) => {
    const line =
      claim?.line_of_business ||
      claim?.coverage ||
      claim?.policy_type ||
      claim?.lob ||
      "Unknown";

    grouped[String(line)] = (grouped[String(line)] || 0) + getClaimIncurred(claim);
  });

  return objectToChartData(grouped);
}

function buildPolicyScheduleLineData() {
  const grouped: Record<string, number> = {};

  policySchedule.forEach((policy: any) => {
    const line =
      policy?.policy_type ||
      policy?.line_coverage ||
      policy?.line_of_business ||
      policy?.coverage ||
      "Policy";

    const policyNumber = normalizePolicyNumber(policy?.policy_number);
    const scheduledIncurred = Number(
      scheduleClaimStats[policyNumber]?.totalIncurred ?? policy?.total_incurred ?? 0
    );

    if (scheduledIncurred > 0) {
      grouped[String(line)] = (grouped[String(line)] || 0) + scheduledIncurred;
    }
  });

  return objectToChartData(grouped);
}

const chartSourceReady = hasActiveAccount && (visibleClaims.length > 0 || claims.length > 0);
const chartTimeline = chartSourceReady ? timeline : {};
const chartBackendMetrics = chartSourceReady ? backendMetrics : {};

const timelineLossTrendData = objectToChartData(chartTimeline?.incurred_by_year || {});
const backendLossTrendData = objectToChartData(chartBackendMetrics?.yearly_incurred || {});
const visibleLossTrendData = buildVisibleClaimYearlyData();
const lossTrendData = chartSourceReady && chartHasData(timelineLossTrendData)
  ? timelineLossTrendData
  : chartSourceReady && chartHasData(backendLossTrendData)
  ? backendLossTrendData
  : chartSourceReady && chartHasData(visibleLossTrendData)
  ? visibleLossTrendData
  : chartSourceReady && totalIncurred > 0
  ? [{ name: "Account Total", value: totalIncurred }]
  : [];

const timelineAgingData = objectToChartData(chartTimeline?.open_claim_aging || {});
const agingData = chartSourceReady && chartHasData(timelineAgingData)
  ? timelineAgingData
  : chartSourceReady && totalClaims > 0
  ? [
      { name: "Open", value: openClaims },
      { name: "Closed", value: closedClaims },
    ]
  : [];

const timelineSeverityData = objectToChartData(chartTimeline?.severity_heatmap || {});
const severityData = chartSourceReady && chartHasData(timelineSeverityData)
  ? timelineSeverityData
  : chartSourceReady && totalClaims > 0
  ? [
      { name: "Standard Claims", value: Math.max(totalClaims - litigationClaims - flaggedClaims, 0) },
      { name: "Flagged", value: flaggedClaims },
      { name: "Litigation", value: litigationClaims },
      { name: "Open", value: openClaims },
    ].filter((item) => Number(item.value || 0) > 0)
  : [];

const timelineLineData = objectToChartData(chartTimeline?.incurred_by_line || {});
const visibleLineData = buildVisibleClaimLineData();
const policyLineData = buildPolicyScheduleLineData();
const lineData = chartSourceReady && chartHasData(timelineLineData)
  ? timelineLineData
  : chartSourceReady && chartHasData(visibleLineData)
  ? visibleLineData
  : chartSourceReady && chartHasData(policyLineData)
  ? policyLineData
  : chartSourceReady && totalIncurred > 0
  ? [{ name: "Account Total", value: totalIncurred }]
  : [];

const reservePressureDisplay =
  chartSourceReady
    ? chartTimeline?.reserve_pressure ||
      (totalReserve > totalIncurred && totalReserve > 0
        ? "High"
        : openClaims > 0
        ? "Elevated"
        : "Low")
    : "-";

const trendNoteDisplay =
  timeline?.trend_note ||
  (totalClaims > 0
    ? `LossQ reviewed ${totalClaims} account-specific claim(s), including ${openClaims} open claim(s), ${litigationClaims} litigation claim(s), $${Number(totalIncurred || 0).toLocaleString()} incurred, and $${Number(totalReserve || 0).toLocaleString()} reserved.`
    : "No trend intelligence available yet.");

// LOSSQ_MODEL_PREDICTION_CHARTS_V1
function lossqChartNumber(value: any): number {
  if (value === null || value === undefined) return 0;
  if (typeof value === "number") return Number.isFinite(value) ? value : 0;

  const cleaned = String(value)
    .replace(/[$,%]/g, "")
    .replace(/[^0-9.-]/g, "")
    .trim();

  const parsed = Number(cleaned);
  return Number.isFinite(parsed) ? parsed : 0;
}

const modelScoreChartData = [
  {
    name: "Renewal Score",
    value: lossqChartNumber(effectiveSummary?.renewal_score),
  },
  {
    name: "Quote Probability",
    value: lossqChartNumber(
      effectiveDecision?.quote_probability ?? effectiveDecision?.renewal_probability
    ),
  },
  {
    name: "Marketability",
    value: lossqChartNumber(effectiveDecision?.marketability_score),
  },
  {
    name: "Carrier Appetite",
    value: lossqChartNumber(effectiveCarrierAppetite?.carrier_appetite_score),
  },
  {
    name: "Submission Readiness",
    value: lossqChartNumber(
      effectiveSubmissionReadiness?.submission_readiness_score ??
        submissionBuilder?.submission_readiness_score
    ),
  },
].filter((item) => Number(item.value || 0) > 0);

const premiumForecastRangeData = [
  {
    name: "Best Case",
    value: lossqChartNumber(effectivePremiumForecast?.best_case_percent),
  },
  {
    name: "Expected",
    value: lossqChartNumber(effectivePremiumForecast?.expected_increase_percent),
  },
  {
    name: "Worst Case",
    value: lossqChartNumber(effectivePremiumForecast?.worst_case_percent),
  },
].filter((item) => Number.isFinite(Number(item.value)));

const modelLineSummarySource =
  effectiveSummary?.renewal_metrics?.line_summary ||
  effectiveDecision?.decision_metrics?.line_summary ||
  effectivePremiumForecast?.forecast_metrics?.line_summary ||
  submissionBuilder?.line_of_business_summary ||
  [];

const modelLossDriverLineData = Array.isArray(modelLineSummarySource)
  ? modelLineSummarySource
      .map((item: any) => ({
        name:
          item?.line_of_business ||
          item?.line ||
          item?.name ||
          item?.coverage ||
          "Unknown",
        incurred: lossqChartNumber(item?.total_incurred),
        reserve: lossqChartNumber(item?.reserve_amount),
        claims: lossqChartNumber(item?.claim_count),
        litigation: lossqChartNumber(item?.litigation_claims),
      }))
      .filter(
        (item: any) =>
          item.incurred > 0 ||
          item.reserve > 0 ||
          item.claims > 0 ||
          item.litigation > 0
      )
      .sort((a: any, b: any) => b.incurred - a.incurred)
      .slice(0, 8)
  : [];

const modelChartNarrative =
  effectiveSummary?.predicted_carrier_reaction ||
  effectivePremiumForecast?.forecast_summary ||
  effectiveDecision?.underwriter_decision_summary ||
  "Model prediction charts will populate after renewal intelligence, carrier appetite, premium forecast, and submission readiness are loaded.";


  if (!authReady) {
    return <LoadingScreen title="Checking session..." subtitle="Validating your LossQ access" />;
  }

  if (dashboardLoading) {
    return <LoadingScreen title="Loading LossQ..." subtitle="Preparing underwriting workspace" />;
  }

  if (dashboardError) {
    return (
      <main className="min-h-screen bg-[#020617] text-white flex items-center justify-center px-6">
{/* LOSSQ_EXTRACTION_REVIEW_BANNER_RENDER_V1 */}
        <LossQExtractionReviewBanner profile={Array.isArray(profiles) && profiles.length > 0 ? profiles[0] : null} />
<div className="absolute inset-0 bg-[radial-gradient(circle_at_top,#1d4ed855,transparent_35%),radial-gradient(circle_at_bottom_right,#0ea5e955,transparent_30%)]" />
        <div className="relative bg-white/10 backdrop-blur-xl border border-red-400/40 rounded-3xl p-10 max-w-lg w-full text-center shadow-2xl">
          <h1 className="text-3xl font-bold mb-4 text-red-300">Dashboard Error</h1>
          <p className="text-slate-300 mb-6">{dashboardError}</p>

          <button
            onClick={() => loadDashboard()}
            className="bg-blue-600 hover:bg-blue-500 px-6 py-3 rounded-xl font-semibold shadow-lg shadow-blue-600/30"
          >
            Retry
          </button>

          <button
            onClick={logout}
            className="block mx-auto mt-4 text-slate-400 hover:text-white text-sm"
          >
            Return to login
          </button>
        </div>
      </main>
    );
  }

  if (!billingLoaded) {
    return (
      <LoadingScreen
        title="Checking billing..."
        subtitle="Confirming your active LossQ subscription before loading dashboard data."
      />
    );
  }

  if (!isDashboardBillingUnlocked()) {
    return (
      <main className="min-h-screen bg-[#050816] text-white flex items-center justify-center px-6">
        <div className="max-w-xl w-full rounded-3xl border border-cyan-400/30 bg-slate-950/90 p-8 shadow-2xl shadow-cyan-500/10">
          <div className="mb-5 inline-flex rounded-full border border-amber-400/40 bg-amber-400/10 px-4 py-2 text-sm font-semibold text-amber-200">
            Payment Required
          </div>

          <h1 className="text-3xl font-black tracking-tight">
            Activate billing to access LossQ
          </h1>

          <p className="mt-4 text-slate-300 leading-relaxed">
            {getDashboardPaymentLockMessage()}
          </p>

          <div className="mt-6 rounded-2xl border border-white/10 bg-white/5 p-4 text-sm text-slate-300">
            This protects the dashboard, claims workspace, uploads, renewal tools,
            carrier packets, reports, and AI underwriting tools from unpaid access.
          </div>

          <div className="mt-7 flex flex-col sm:flex-row gap-3">
            <button
              type="button"
              onClick={() => router.push("/pricing?required=dashboard")}
              className="rounded-xl bg-cyan-400 px-5 py-3 font-bold text-slate-950 hover:bg-cyan-300"
            >
              Choose a Plan
            </button>

            <button
              type="button"
              onClick={() => window.location.reload()}
              className="rounded-xl border border-white/15 px-5 py-3 font-bold text-white hover:bg-white/10"
            >
              Refresh Billing
            </button>


              <button
                type="button"
                onClick={openBetaFeedbackEmail}
                className="rounded-xl border border-cyan-400/30 bg-cyan-400/10 px-4 py-2 text-sm font-semibold text-cyan-100 hover:bg-cyan-400/20"
              >
                Report Issue
              </button>
<button
              type="button"
              onClick={logout}
              className="rounded-xl border border-red-400/30 px-5 py-3 font-bold text-red-200 hover:bg-red-500/10"
            >
              Log Out
            </button>
          </div>
        </div>
      </main>
    );
  }

  return (
    <main className="min-h-screen bg-[#020617] text-white overflow-x-hidden">
      <div className="fixed inset-0 bg-[radial-gradient(circle_at_top_left,#1d4ed866,transparent_28%),radial-gradient(circle_at_top_right,#0ea5e955,transparent_30%),radial-gradient(circle_at_bottom,#312e8155,transparent_35%)]" />
      <div className="fixed inset-0 bg-[linear-gradient(to_right,rgba(255,255,255,0.04)_1px,transparent_1px),linear-gradient(to_bottom,rgba(255,255,255,0.04)_1px,transparent_1px)] bg-[size:72px_72px] opacity-20" />

      <div className="relative flex min-h-screen">
        <aside
  className="hidden lg:flex fixed left-4 top-4 bottom-4 w-72 shrink-0 flex-col rounded-3xl border border-white/10 bg-slate-950/85 backdrop-blur-2xl p-5 z-50 overflow-y-auto shadow-[0_0_50px_rgba(59,130,246,0.18)]"
>
  <div className="mb-8">
    <img
      src="/lossq-logo-style2.png"
      alt="LossQ"
      className="w-full rounded-2xl border border-blue-400/20 shadow-[0_0_35px_rgba(59,130,246,0.22)]"
    />

    <div className="mt-4 text-center">
      <div className="text-xs uppercase tracking-[0.35em] text-blue-300">
        Underwriting Intelligence Platform
      </div>
    </div>
  </div>

  <ToolButton active={activeTool === "overview"} onClick={() => changeActiveTool("overview")}>
    Overview
  </ToolButton>

  <ToolButton active={activeTool === "profiles"} onClick={() => changeActiveTool("profiles")}>
    Carrier Profiles
  </ToolButton>

  <ToolButton active={activeTool === "upload"} onClick={() => changeActiveTool("upload")}>
    Upload Center
  </ToolButton>

  <ToolButton active={activeTool === "exposure-inputs"} onClick={() => changeActiveTool("exposure-inputs")}>
    Exposure Inputs
  </ToolButton>

  <ToolButton active={activeTool === "submission-builder"} onClick={() => changeActiveTool("submission-builder")}>
    Submission Builder
  </ToolButton>

  <ToolButton active={activeTool === "renewal-risk"} onClick={() => changeActiveTool("renewal-risk")}>
    Renewal Risk
  </ToolButton>

  <ToolButton active={activeTool === "premium-forecast"} onClick={() => changeActiveTool("premium-forecast")}>
    Premium Forecast
  </ToolButton>

  <ToolButton active={activeTool === "decision"} onClick={() => changeActiveTool("decision")}>
    Underwriter Decision
  </ToolButton>

  <ToolButton active={activeTool === "carrier-appetite"} onClick={() => setActiveTool("carrier-appetite")}>
    Carrier Appetite
  </ToolButton>

  <ToolButton active={activeTool === "submission-readiness"} onClick={() => setActiveTool("submission-readiness")}>
    Submission Readiness
  </ToolButton>

  <ToolButton active={activeTool === "carrier-match"} onClick={() => changeActiveTool("carrier-match")}>
    Carrier Match
  </ToolButton>

  <ToolButton active={activeTool === "summary"} onClick={() => changeActiveTool("summary")}>
    AI Summary
  </ToolButton>

  <ToolButton active={activeTool === "memo"} onClick={() => changeActiveTool("memo")}>
    Renewal Memo
  </ToolButton>

  <ToolButton active={activeTool === "charts"} onClick={() => changeActiveTool("charts")}>
    Charts
  </ToolButton>

  <ToolButton active={activeTool === "claims"} onClick={() => changeActiveTool("claims")}>
    Claims
  </ToolButton>

  <div className="mt-auto space-y-3 pt-6 border-t border-white/10">
    {/* LOSSQ_VISIBLE_REPORT_ISSUE_NAVBUTTON_V1 */}
    <button
      type="button"
      onClick={openBetaFeedbackEmail}
      className="w-full rounded-xl border border-yellow-300/60 bg-yellow-300 px-5 py-3 font-bold text-slate-950 shadow-lg shadow-yellow-300/30 hover:bg-yellow-200"
    >
      Report Issue
    </button>

    <NavButton href="/settings">Settings</NavButton>

    <a
      href="/carrier-workspace"
      className="btn-purple block text-center"
    >
      Carrier Workspace
    </a>

    <button
      onClick={logout}
      className="btn-danger w-full"
    >
      Logout
    </button>
  </div>
</aside>

        <section className="flex-1 px-4 sm:px-5 md:px-8 py-6 md:py-8 pb-32 max-w-7xl mx-auto w-full lg:ml-72">
          <header className="flex flex-col gap-6 lg:flex-row lg:items-center lg:justify-between mb-8">
            <div>
              <div className="inline-flex items-center gap-2 rounded-full border border-blue-400/30 bg-blue-500/10 px-4 py-2 text-sm text-blue-200 mb-5">
                <span className="h-2 w-2 rounded-full bg-blue-400 shadow-[0_0_18px_#60a5fa]" />
                AI Underwriting Command Center
              </div>

              <h1 className="text-4xl md:text-6xl font-black tracking-tight leading-tight break-words">
                LossQ Dashboard
              </h1>

          {betaAccessLabel && (
            <div className="mt-3 inline-flex rounded-full border border-cyan-400/30 bg-cyan-400/10 px-4 py-2 text-xs font-bold uppercase tracking-[0.18em] text-cyan-100">
              {betaAccessLabel}
            </div>
          )}


              <p className="text-slate-300 mt-3 max-w-2xl">
                Select a tool from the sidebar to analyze claims, renewal risk, underwriting decisions, reports, and carrier strategy.
              </p>
            </div>

            <div className="flex flex-wrap gap-3">
              <button onClick={() => setCopilotOpen(true)} className="btn-primary">
                Open Copilot
              </button>
              <button onClick={logout} className="btn-danger lg:hidden">
                Logout
              </button>
            </div>
          </header>


          {showNewUserWelcome && (
            <div className="mb-8 rounded-3xl border border-cyan-400/30 bg-cyan-400/10 p-6 shadow-[0_0_40px_rgba(34,211,238,0.12)]">
              <div className="flex flex-col gap-5 lg:flex-row lg:items-start lg:justify-between">
                <div className="max-w-3xl">
                  <div className="mb-3 inline-flex items-center gap-2 rounded-full border border-cyan-300/30 bg-cyan-300/10 px-3 py-1 text-xs font-black uppercase tracking-[0.2em] text-cyan-200">
                    Welcome to LossQ
                  </div>

                  <h2 className="text-2xl font-black tracking-tight text-white">
                    Welcome, {newUserWelcomeName || "there"}.
                  </h2>

                  <p className="mt-2 text-sm font-semibold text-cyan-100">
                    Your underwriting workspace is ready.
                  </p>

                  <p className="mt-3 max-w-3xl text-sm leading-7 text-slate-300">
                    LossQ was built to help brokers and agencies turn loss runs into carrier-ready underwriting intelligence. Start by uploading a loss run, reviewing the account profile, adding exposure inputs, and then generating renewal risk, carrier appetite, premium forecast, submission packets, and carrier email drafts from one place.
                  </p>

                  <div className="mt-5 grid gap-3 md:grid-cols-3">
                    <div className="rounded-2xl border border-white/10 bg-white/[0.04] p-4">
                      <p className="text-sm font-black text-white">1. Upload loss runs</p>
                      <p className="mt-1 text-xs leading-5 text-slate-400">
                        Import PDF, CSV, or Excel files and let LossQ organize claim activity.
                      </p>
                    </div>

                    <div className="rounded-2xl border border-white/10 bg-white/[0.04] p-4">
                      <p className="text-sm font-black text-white">2. Add exposure inputs</p>
                      <p className="mt-1 text-xs leading-5 text-slate-400">
                        Add premium, payroll, revenue, drivers, vehicles, limits, and underwriting context.
                      </p>
                    </div>

                    <div className="rounded-2xl border border-white/10 bg-white/[0.04] p-4">
                      <p className="text-sm font-black text-white">3. Build the submission</p>
                      <p className="mt-1 text-xs leading-5 text-slate-400">
                        Generate carrier packets, renewal memos, and prefilled carrier email drafts.
                      </p>
                    </div>
                  </div>
                </div>

                <div className="flex shrink-0">
                  <button
                    onClick={dismissNewUserWelcome}
                    className="rounded-xl border border-white/10 px-4 py-2 text-sm font-bold text-slate-300 transition hover:bg-white/10 hover:text-white"
                  >
                    Got it
                  </button>
                </div>
              </div>
            </div>
          )}



          <div className="lg:hidden glass-panel p-3 mb-6 overflow-x-auto sticky top-3 z-40">
            <div className="flex gap-2 min-w-max">
              <MobileToolButton active={activeTool === "overview"} onClick={() => changeActiveTool("overview")}>Overview</MobileToolButton>
              <MobileToolButton active={activeTool === "profiles"} onClick={() => changeActiveTool("profiles")}>Profiles</MobileToolButton>
              <MobileToolButton active={activeTool === "upload"} onClick={() => changeActiveTool("upload")}>Upload</MobileToolButton>
              {/* LOSSQ_MOBILE_REPORT_SETTINGS_NAV_V1 */}
              <button
                type="button"
                onClick={openBetaFeedbackEmail}
                className="shrink-0 rounded-xl border border-yellow-300/60 bg-yellow-300 px-4 py-3 text-sm font-bold text-slate-950 shadow-lg shadow-yellow-300/20"
              >
                Report Issue
              </button>
              <a
                href="/settings"
                className="shrink-0 rounded-xl border border-white/15 bg-white/10 px-4 py-3 text-sm font-bold text-white hover:bg-white/15"
              >
                Settings
              </a>
              <MobileToolButton active={activeTool === "exposure-inputs"} onClick={() => changeActiveTool("exposure-inputs")}>Exposure Inputs</MobileToolButton>
              <MobileToolButton active={activeTool === "renewal-risk"} onClick={() => changeActiveTool("renewal-risk")}>Renewal Risk</MobileToolButton>
              <MobileToolButton active={activeTool === "decision"} onClick={() => changeActiveTool("decision")}>Decision</MobileToolButton>
              <MobileToolButton active={activeTool === "carrier-appetite"} onClick={() => setActiveTool("carrier-appetite")}>Carrier Appetite</MobileToolButton>
              <MobileToolButton active={activeTool === "submission-readiness"} onClick={() => setActiveTool("submission-readiness")}>Submission Readiness</MobileToolButton>
              <MobileToolButton active={activeTool === "carrier-match"} onClick={() => changeActiveTool("carrier-match")}>Carrier Match</MobileToolButton>
<MobileToolButton active={activeTool === "premium-forecast"} onClick={() => changeActiveTool("premium-forecast")}>
  Premium Forecast
</MobileToolButton>
<MobileToolButton active={activeTool === "submission-builder"} onClick={() => changeActiveTool("submission-builder")}>
  Submission Builder
</MobileToolButton>
              <MobileToolButton active={activeTool === "summary"} onClick={() => changeActiveTool("summary")}>Summary</MobileToolButton>
              <MobileToolButton active={activeTool === "memo"} onClick={() => changeActiveTool("memo")}>Memo</MobileToolButton>
              <MobileToolButton active={activeTool === "charts"} onClick={() => changeActiveTool("charts")}>Charts</MobileToolButton>
              <MobileToolButton active={activeTool === "claims"} onClick={() => changeActiveTool("claims")}>Claims</MobileToolButton>
            </div>
          </div>

          {message && (
            <div className="glass-panel mb-6 p-4 text-slate-200 border-blue-400/20">
              {message}
            </div>
          )}

          {activeTool === "overview" && (
            <>
              <section className="grid grid-cols-1 md:grid-cols-4 gap-5 mb-8">
                <MetricCard title="Total Claims" value={totalClaimsDisplay} />
                <MetricCard title="Open Claims" value={openClaimsDisplay} />
                <MetricCard title="Total Incurred" value={totalIncurredDisplay} />
                <MetricCard title="Renewal Score" value={effectiveSummary?.renewal_score ?? "-"} />
              </section>

              <section className="grid grid-cols-1 md:grid-cols-4 gap-5 mb-8">
                <MetricCard title="Risk Level" value={effectiveSummary?.renewal_risk_level || "Not Rated"} />
                <MetricCard title="Renewal Probability" value={effectiveDecision?.renewal_probability != null ? `${effectiveDecision.renewal_probability}%` : "-"} />
                <MetricCard title="Carrier Appetite" value={effectiveCarrierAppetite?.carrier_appetite_score != null ? `${effectiveCarrierAppetite.carrier_appetite_score}/100` : "-"} />
                <MetricCard title="Submission Readiness" value={effectiveSubmissionReadiness?.submission_readiness_score != null ? `${effectiveSubmissionReadiness.submission_readiness_score}/100` : "-"} />
              </section>

              <section className="glass-panel p-6 md:p-8">
                <h2 className="text-2xl md:text-3xl font-bold mb-4">Account Snapshot</h2>

                <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
                  <ProfileDetail label="Insured" value={displayProfile?.business_name || "-"} />
                  <ProfileDetail
                    label="Writing Carrier"
                    value={displayProfile?.writing_carrier || displayProfile?.carrier_name || "-"}
                  />
                  <ProfileDetail label="Carrier" value={lossqSafeCarrierDisplay(displayProfile)} />
                  <ProfileDetail
                    label="Account Number"
                    value={displayProfile?.account_number || displayProfile?.customer_number || "-"}
                  />
                  <ProfileDetail label="Producing Agency" value={lossqProducingAgencyFromObject(displayProfile)} />
                  <ProfileDetail label="Main Policy" value={mainPolicyNumber || "-"} />
                  <ProfileDetail label="Effective Date" value={lossqEffectiveDateFromObject(displayProfile) || lossqFirstPolicyEffectiveDate(policySchedule) || "Not set"} />
                  <ProfileDetail label="Expiration Date" value={lossqExpirationDateFromObject(displayProfile) || lossqFirstPolicyExpirationDate(policySchedule) || "Not set"} />
                  <ProfileDetail label="Evaluation Date" value={getBestEvaluationDate(displayProfile) || lossqAnyEvaluationDate(displayProfile) || lossqFirstPolicyEvaluationDate(policySchedule) || "Not set"} />
                </div>

                <EvaluationDateAlertBadge profileLike={displayProfile} policyRows={policySchedule} />

                {policySchedule.length > 0 && (
                  <div className="mt-8 rounded-3xl border border-white/10 bg-slate-950/50 p-5">
                    <div className="mb-4">
                      <p className="text-xs uppercase tracking-[0.25em] text-blue-300">
                        Policies on Account
                      </p>
                      <h3 className="mt-2 text-xl font-bold text-white">Policy Schedule</h3>
                      <p className="mt-1 text-sm text-slate-400">
                        Policy Number, Line / Coverage, policy period, claim count, and total incurred.
                      </p>
                    </div>

                    <div className="overflow-x-auto">
                      <table className="w-full min-w-[840px] text-sm">
                        <thead>
                          <tr className="border-b border-white/10 text-left text-slate-300">
                            <th className="py-3 pr-4">Policy Type / Coverage</th>
                            <th className="py-3 pr-4">Policy Number</th>
                            {/* LOSSQ_REMOVE_DUPLICATE_WRITING_CARRIER_COLUMN_V1 */}
                            <th className="py-3 pr-4">Carrier</th>
                            <th className="py-3 pr-4">Effective</th>
                            <th className="py-3 pr-4">Expiration</th>
                            <th className="py-3 pr-4">Claims</th>
                            <th className="py-3 pr-4">Total Incurred</th>
                          </tr>
                        </thead>

                        <tbody>
                          {lossqStrictCleanPolicySchedule(policySchedule).map((policy: any, index: number) => {
                            // LOSSQ_POLICY_SCHEDULE_TABLE_CLEAN_RENDER_V1
                            const policyNumber = normalizePolicyNumber(policy?.policy_number);
                            const stats = scheduleClaimStats[policyNumber];

                            const rowCarrier = cleanScheduleCarrier(
                              policy?.carrier || policy?.carrier_name,
                              displayProfile?.carrier_name || displayProfile?.writing_carrier
                            );

                            const rowEffectiveDate =
                              lossqAnyEffectiveDate(policy) ||
                              lossqAnyEffectiveDate(displayProfile) ||
                              lossqAnyEffectiveDate(profile) ||
                              lossqFirstPolicyEffectiveDate(policySchedule) ||
                              "-";

                            const rowExpirationDate =
                              lossqAnyExpirationDate(policy) ||
                              lossqAnyExpirationDate(displayProfile) ||
                              lossqAnyExpirationDate(profile) ||
                              lossqFirstPolicyExpirationDate(policySchedule) ||
                              "-";

                            return (
                              <tr
                                key={policy?.policy_number || index}
                                className="border-b border-white/10"
                              >
                                <td className="py-3 pr-4 text-white">
                                  {lossqLineOfBusinessFromObject(policy)}
                                </td>
                                <td className="py-3 pr-4 font-semibold text-blue-200">
                                  {lossqPolicyNumberFromObject(policy)}
                                </td>
                                <td className="py-3 pr-4">{rowCarrier}</td>
                                <td className="py-3 pr-4">{rowEffectiveDate}</td>
                                <td className="py-3 pr-4">{rowExpirationDate}</td>
                                <td className="py-3 pr-4">
                                  {stats?.count ?? policy?.claim_count ?? 0}
                                </td>
                                <td className="py-3 pr-4">
                                  ${Number(stats?.totalIncurred ?? policy?.total_incurred ?? 0).toLocaleString()}
                                </td>
                              </tr>
                            );
                          })}
                        </tbody>
                      </table>
                    </div>
                  </div>
                )}
              </section>

              {Array.isArray(profile?.policies) && profile.policies.length > 0 && (
                <section className="glass-panel p-6 md:p-8 mt-6">
                  <div className="flex flex-col gap-2 mb-5">
                    <h2 className="text-2xl md:text-3xl font-bold">
                      Policy Lines / Coverage Schedule
                    </h2>
                    <p className="text-sm text-slate-400">
                      Multiple lines of business detected from this uploaded loss run.
                    </p>
                  </div>

                  <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
                    {profile.policies.map((pol: any, index: number) => {
                      const policyNumber =
                        pol?.policy_number ||
                        pol?.policy_no ||
                        pol?.policy ||
                        pol?.account_number ||
                        "";

                      const lineOfBusiness =
                        pol?.line_of_business ||
                        pol?.lob ||
                        pol?.coverage_line ||
                        pol?.coverage ||
                        pol?.policy_line ||
                        pol?.line ||
                        "Commercial Line";

                      const carrierName =
                        pol?.carrier_name ||
                        pol?.writing_carrier ||
                        profile?.carrier_name ||
                        profile?.writing_carrier ||
                        "Carrier Not Set";

                      const effectiveDate =
                        lossqAnyEffectiveDate(pol) ||
                        lossqAnyEffectiveDate(displayProfile) ||
                        lossqAnyEffectiveDate(profile) ||
                        lossqFirstPolicyEffectiveDate(policySchedule) ||
                        "Not Set";

                      const expirationDate =
                        lossqAnyExpirationDate(pol) ||
                        lossqAnyExpirationDate(displayProfile) ||
                        lossqAnyExpirationDate(profile) ||
                        lossqFirstPolicyExpirationDate(policySchedule) ||
                        "Not Set";

                      const policyClaimCount = claims.filter((claim: any) => {
                        const claimPolicy = normalizePolicyNumber(claim?.policy_number);
                        const schedulePolicy = normalizePolicyNumber(policyNumber);
                        const claimLob = String(
                          claim?.line_of_business ||
                          claim?.lob ||
                          claim?.coverage_line ||
                          ""
                        ).toLowerCase();

                        const scheduleLob = String(lineOfBusiness || "").toLowerCase();

                        return (
                          (schedulePolicy && claimPolicy === schedulePolicy) ||
                          (scheduleLob && claimLob && claimLob.includes(scheduleLob))
                        );
                      }).length;

                      return (
                        <div
                          key={`${policyNumber || lineOfBusiness}-${index}`}
                          className="rounded-2xl border border-white/10 bg-white/5 p-5"
                        >
                          <p className="text-xs uppercase tracking-[0.25em] text-blue-300 mb-2">
                            {lineOfBusiness}
                          </p>

                          <div className="space-y-2 text-sm">
                            <div>
                              <p className="text-slate-400">Policy Number</p>
                              <p className="font-semibold text-white">
                                {policyNumber || "Not Set"}
                              </p>
                            </div>

                            <div>
                              <p className="text-slate-400">Carrier</p>
                              <p className="font-semibold text-white">
                                {carrierName}
                              </p>
                            </div>

                            <div className="grid grid-cols-2 gap-3">
                              <div>
                                <p className="text-slate-400">Effective</p>
                                <p className="font-semibold text-white">
                                  {effectiveDate}
                                </p>
                              </div>

                              <div>
                                <p className="text-slate-400">Expiration</p>
                                <p className="font-semibold text-white">
                                  {expirationDate}
                                </p>
                              </div>
                            </div>

                            <div>
                              <p className="text-slate-400">Claims</p>
                              <p className="font-semibold text-white">
                                {policyClaimCount}
                              </p>
                            </div>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </section>
              )}

            </>
          )}



          {activeTool === "profiles" && (
            <>
              <section className="glass-panel p-6 md:p-8 mb-8">
                <div className="flex flex-col gap-6 lg:flex-row lg:items-end lg:justify-between">
                  <div className="flex-1">
                    <h2 className="text-2xl md:text-3xl font-bold">Carrier Profile Workspace</h2>
                    <p className="text-slate-400 mt-2">
                      Select a saved carrier profile or create a new company profile.
                    </p>

                    <div className="mt-6 max-w-2xl">
                      <label className="block text-sm text-blue-200 mb-2">
                        Saved Carrier Profiles
                      </label>

                      <select
                        value={profile?.policy_number || ""}
                        onChange={(e) => selectAccount(e.target.value)}
                        className="w-full rounded-2xl bg-slate-950/70 border border-white/10 px-4 py-4 text-white outline-none focus:border-blue-400 focus:ring-4 focus:ring-blue-500/20"
                      >
                        <option value="">Select saved profile...</option>
                        {profiles.map((item) => (
                          <option key={item.id || item.policy_number} value={item.policy_number}>
                            {(getAccountDisplayName(item) || "Unnamed Business") +
                              " - " +
                              (item.policy_number || "No Policy Number")}
                          </option>
                        ))}
                      </select>
                    </div>
                  </div>

                  <div className="flex flex-wrap gap-3">
                    <button onClick={newBlankProfile} className="btn-secondary">
                      New Company Profile
                    </button>

                    {profile?.policy_number && (
                      <button
                        type="button"
                        onClick={() => deleteProfile(profile)}
                        className="btn-danger"
                      >
                        Delete Profile
                      </button>
                    )}
                  </div>
                </div>
              </section>

              <section className="glass-panel p-6 md:p-8">
                <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between mb-6">
                  <h2 className="text-2xl md:text-3xl font-bold">Carrier Account Profile</h2>

                  <div className="flex gap-3">
                    <button onClick={lookupPolicy} className="btn-secondary">Lookup</button>
                    <button onClick={saveProfile} className="btn-success">Save Profile</button>
                  </div>
                </div>

                {/* LOSSQ_EXPOSURE_INPUT_DISPLAY_MERGE_V1 */}
              {(() => {
                const exposureProfile: any = {
                  ...(profile || {}),
                  ...(displayProfile || {}),
                };

                const exposureValue = (field: string) =>
                  exposureProfile?.[field] ||
                  profile?.[field] ||
                  displayProfile?.[field] ||
                  "";

                return null;
              })()}

              <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
                  <Input label="Insured" value={profile?.business_name || ""} onChange={(v) => setProfile({ ...profile, business_name: v })} />
                  <Input label="Writing Carrier" value={profile?.carrier_name || ""} onChange={(v) => setProfile({ ...profile, carrier_name: v })} />
                  <Input label="Producing Agency" value={profile?.agency_name || ""} onChange={(v) => setProfile({ ...profile, agency_name: v })} />
                  <Input label="Policy Number" value={profile?.policy_number || ""} onChange={(v) => setProfile({ ...profile, policy_number: v })} />
                  <Input label="Effective Date" value={profile?.effective_date || ""} onChange={(v) => setProfile({ ...profile, effective_date: v })} />
                  <Input label="Expiration Date" value={profile?.expiration_date || ""} onChange={(v) => setProfile({ ...profile, expiration_date: v })} />
                  <Input label="Evaluation Date" value={getBestEvaluationDate(profile) || lossqAnyEvaluationDate(displayProfile) || lossqFirstPolicyEvaluationDate(policySchedule) || ""} onChange={(v) => setProfile({ ...profile, evaluation_date: v })} />
                </div>
              </section>
            </>
          )}


          {activeTool === "exposure-inputs" && (
            <section className="glass-panel p-6 md:p-8">
              <p className="text-sm uppercase tracking-[0.25em] text-green-300 mb-3">
                Universal Forecast Inputs
              </p>

              <h2 className="text-2xl md:text-3xl font-bold mb-4">
                Manual Premium & Exposure Inputs
              </h2>

              <p className="text-slate-400 mb-8 max-w-4xl">
                LossQ auto-fills premium, exposure, limits, class, and underwriting data from the selected loss run when available. You can manually edit any field, and manual edits override auto-filled values.
              </p>

              <div className="rounded-3xl border border-blue-400/20 bg-blue-500/10 p-5 mb-8">
                <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
                  <ProfileDetail label="Account" value={displayProfile?.business_name || profile?.business_name || "-"} />
                  <ProfileDetail label="Main Policy" value={displayProfile?.policy_number || profile?.policy_number || "-"} />
                  <ProfileDetail label="Account Number" value={lossqDisplayAccountNumber(displayProfile) || lossqDisplayAccountNumber(profile) || "-"} />
                  <ProfileDetail label="Carrier" value={displayProfile?.carrier_name || profile?.carrier_name || "-"} />
                  <ProfileDetail label="Detected Lines" value={policySchedule.length > 0 ? `${policySchedule.length} line(s)` : "Manual Input"} />
                </div>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
                <Input label="Current Premium" value={displayProfile?.current_premium || profile?.current_premium || deriveExposureInputsFromPolicyRows(profile)?.current_premium || ""} onChange={(v) => setProfile({ ...profile, current_premium: v })} />
                <Input label="Expiring Premium" value={displayProfile?.expiring_premium || profile?.expiring_premium || deriveExposureInputsFromPolicyRows(profile)?.expiring_premium || ""} onChange={(v) => setProfile({ ...profile, expiring_premium: v })} />
                <Input label="Target Renewal Premium" value={displayProfile?.target_renewal_premium || profile?.target_renewal_premium || deriveExposureInputsFromPolicyRows(profile)?.target_renewal_premium || ""} onChange={(v) => setProfile({ ...profile, target_renewal_premium: v })} />

                <Input label="Primary Line of Business" value={displayProfile?.line_of_business || profile?.line_of_business || deriveExposureInputsFromPolicyRows(profile)?.line_of_business || ""} onChange={(v) => setProfile({ ...profile, line_of_business: v })} />
                <Input label="State" value={displayProfile?.state || profile?.state || deriveExposureInputsFromPolicyRows(profile)?.state || ""} onChange={(v) => setProfile({ ...profile, state: v })} />
                <Input label="Class Code(s)" value={profile?.class_code || editableProfileValue("class_codes")} onChange={(v) => setProfile({ ...profile, class_code: v, class_codes: v })} />

                <Input label="Policy Limits" value={safePolicyLimitsValue()} onChange={(v) => setProfile({ ...profile, limits: v, coverage_limit: v })} />
                <Input label="Deductible" value={displayProfile?.deductible || profile?.deductible || deriveExposureInputsFromPolicyRows(profile)?.deductible || ""} onChange={(v) => setProfile({ ...profile, deductible: v })} />
                <Input label="Retention / SIR" value={displayProfile?.retention || profile?.retention || deriveExposureInputsFromPolicyRows(profile)?.retention || ""} onChange={(v) => setProfile({ ...profile, retention: v })} />

                <Input label="Payroll" value={displayProfile?.payroll || profile?.payroll || deriveExposureInputsFromPolicyRows(profile)?.payroll || ""} onChange={(v) => setProfile({ ...profile, payroll: v })} />
                <Input label="Revenue / Sales" value={profile?.revenue || editableProfileValue("sales")} onChange={(v) => setProfile({ ...profile, revenue: v, sales: v })} />
                <Input label="Receipts" value={displayProfile?.receipts || profile?.receipts || deriveExposureInputsFromPolicyRows(profile)?.receipts || ""} onChange={(v) => setProfile({ ...profile, receipts: v })} />

                <Input label="Employee Count" value={displayProfile?.employee_count || profile?.employee_count || deriveExposureInputsFromPolicyRows(profile)?.employee_count || ""} onChange={(v) => setProfile({ ...profile, employee_count: v })} />
                <Input label="Vehicle Count" value={displayProfile?.vehicle_count || profile?.vehicle_count || deriveExposureInputsFromPolicyRows(profile)?.vehicle_count || ""} onChange={(v) => setProfile({ ...profile, vehicle_count: v })} />
                <Input label="Driver Count" value={displayProfile?.driver_count || profile?.driver_count || deriveExposureInputsFromPolicyRows(profile)?.driver_count || ""} onChange={(v) => setProfile({ ...profile, driver_count: v })} />

                <Input label="Property TIV" value={profile?.property_tiv || editableProfileValue("tiv")} onChange={(v) => setProfile({ ...profile, property_tiv: v, tiv: v })} />
                <Input label="Building Value" value={displayProfile?.building_value || profile?.building_value || deriveExposureInputsFromPolicyRows(profile)?.building_value || ""} onChange={(v) => setProfile({ ...profile, building_value: v })} />
                <Input label="Contents Value" value={displayProfile?.contents_value || profile?.contents_value || deriveExposureInputsFromPolicyRows(profile)?.contents_value || ""} onChange={(v) => setProfile({ ...profile, contents_value: v })} />

                <Input label="Square Footage" value={displayProfile?.square_footage || profile?.square_footage || deriveExposureInputsFromPolicyRows(profile)?.square_footage || ""} onChange={(v) => setProfile({ ...profile, square_footage: v })} />
                <Input label="Location Count" value={displayProfile?.location_count || profile?.location_count || deriveExposureInputsFromPolicyRows(profile)?.location_count || ""} onChange={(v) => setProfile({ ...profile, location_count: v })} />
                <Input label="Unit Count" value={displayProfile?.unit_count || profile?.unit_count || deriveExposureInputsFromPolicyRows(profile)?.unit_count || ""} onChange={(v) => setProfile({ ...profile, unit_count: v })} />

                <Input label="Cargo Limit" value={displayProfile?.cargo_limit || profile?.cargo_limit || deriveExposureInputsFromPolicyRows(profile)?.cargo_limit || ""} onChange={(v) => setProfile({ ...profile, cargo_limit: v })} />
                <Input label="Umbrella / Excess Limit" value={displayProfile?.umbrella_limit || profile?.umbrella_limit || deriveExposureInputsFromPolicyRows(profile)?.umbrella_limit || ""} onChange={(v) => setProfile({ ...profile, umbrella_limit: v })} />
                <Input label="Experience Mod" value={profile?.experience_mod || editableProfileValue("mod")} onChange={(v) => setProfile({ ...profile, experience_mod: v, mod: v })} />

                <Input label="Exposure Change %" value={displayProfile?.exposure_change_percent || profile?.exposure_change_percent || deriveExposureInputsFromPolicyRows(profile)?.exposure_change_percent || ""} onChange={(v) => setProfile({ ...profile, exposure_change_percent: v })} />
                <Input label="Cyber Revenue" value={displayProfile?.cyber_revenue || profile?.cyber_revenue || deriveExposureInputsFromPolicyRows(profile)?.cyber_revenue || ""} onChange={(v) => setProfile({ ...profile, cyber_revenue: v })} />
                <Input label="Professional Revenue" value={displayProfile?.professional_revenue || profile?.professional_revenue || deriveExposureInputsFromPolicyRows(profile)?.professional_revenue || ""} onChange={(v) => setProfile({ ...profile, professional_revenue: v })} />
              </div>

              <div className="mt-6">
                <label className="block text-sm text-blue-200 mb-2">
                  Notes / Underwriter Comments
                </label>
                <textarea
                  value={editableProfileValue("underwriter_notes")}
                  onChange={(e) => setProfile({ ...profile, underwriter_notes: e.target.value })}
                  className="w-full min-h-[150px] rounded-2xl bg-slate-950/70 border border-white/10 px-4 py-4 text-white outline-none focus:border-blue-400 focus:ring-4 focus:ring-blue-500/20"
                  placeholder="Enter exposure assumptions, underwriting notes, class details, loss control updates, or renewal pricing assumptions..."
                />
              </div>

              <div className="mt-8 flex flex-wrap gap-4">
                <button
                  type="button"
                  onClick={autoFillExposureInputsFromUpload}
                  className="btn-primary"
                >
                  Auto-Fill From Loss Run
                </button>

                {/* LOSSQ_EXPOSURE_AUTOFILL_BUTTON_V1 */}
                <button onClick={saveExposureInputs} className="btn-success">
                  Save Exposure Inputs
                </button>
                <button onClick={() => changeActiveTool("premium-forecast")} className="btn-purple">
                  Open Premium Forecast
                </button>
              </div>
            </section>
          )}

          {activeTool === "upload" && (
            <section className="glass-panel p-6 md:p-8">
              <h2 className="text-2xl md:text-3xl font-bold mb-5">Upload & Report Center</h2>

              <div className="flex flex-col sm:flex-row sm:flex-wrap gap-4 items-stretch sm:items-center">
                <input
                  type="file"
                  multiple
                  accept=".pdf,.xlsx,.csv"
                  onChange={(e) => setFiles(e.target.files)}
                  className="text-sm text-slate-300 file:mr-4 file:rounded-xl file:border-0 file:bg-blue-600 file:px-4 file:py-3 file:text-white file:font-semibold"
                />

                <button onClick={uploadFiles} disabled={isUploading} className="btn-primary" style={{opacity: isUploading ? 0.5 : 1, cursor: isUploading ? 'not-allowed' : 'pointer'}}>{isUploading ? "Uploading..." : "Upload & Analyze"}</button>
                <button onClick={exportCarrierLossRun} className="btn-success">Export Carrier Loss Run</button>
                <button onClick={exportExecutiveReport} className="btn-success">Export Executive Report</button>
                <button onClick={generateCarrierPacket} className="btn-purple">Generate Carrier Packet</button>
                <a href="/review" className="btn-secondary">Review Extraction</a>
                <a href="/carrier-workspace" className="btn-purple">Carrier Workspace</a>
              </div>
            </section>
          )}

          {activeTool === "renewal-risk" && (
            <section className="glass-panel p-6 md:p-8">
              <div className="flex flex-col gap-6 lg:flex-row lg:items-start lg:justify-between">
                <div>
                  <p className="text-sm uppercase tracking-[0.25em] text-blue-300 mb-3">
                    Renewal Risk Engine
                  </p>

                  <h2 className="text-2xl md:text-3xl font-bold">
                    Renewal Risk Score
                  </h2>

                  <p className="text-slate-400 mt-2 max-w-3xl">
                    Policy-specific renewal risk based on claims, reserves, severity,
                    litigation, frequency, and open claim pressure.
                  </p>
                </div>

                <div className="rounded-3xl border border-white/10 bg-slate-950/70 px-8 py-6 text-center min-w-[180px]">
                  <div className="text-5xl font-black">
                    {effectiveSummary?.renewal_score ?? "-"}
                  </div>
                  <div className="text-slate-400 text-sm mt-1">out of 100</div>

                  <div className="mt-4 inline-flex rounded-full border border-blue-400/30 bg-blue-500/10 px-4 py-2 text-sm font-bold text-blue-200">
                    {effectiveSummary?.renewal_risk_level || "Not Rated"}
                  </div>
                </div>
              </div>

              <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mt-8">
                <ListCard title="Renewal Drivers" items={effectiveSummary?.renewal_drivers || ["No renewal drivers available."]} color="blue" />
                <ListCard title="Carrier Concerns" items={effectiveSummary?.carrier_concerns || ["No carrier concerns available."]} color="red" />

                {/* LOSSQ_FRONTEND_SAFETY_CLAIM_STORY_DISPLAY_V1 */}
                <div className="lg:col-span-2">
                  <ListCard
                    title="Safety & Risk Recommendations"
                    items={
                      effectiveSummary?.safety_recommendations ||
                      effectiveSummary?.risk_control_recommendations ||
                      ["No safety and risk recommendations available yet."]
                    }
                    color="blue"
                  />
                </div>

                <div className="lg:col-span-2">
                  <ListCard
                    title="Loss-Control Plan"
                    items={
                      effectiveSummary?.loss_control_plan ||
                      effectiveSummary?.carrier_risk_improvement_plan ||
                      ["No loss-control plan available yet."]
                    }
                    color="purple"
                  />
                </div>

                <div className="lg:col-span-2">
                  <ListCard
                    title="Recommended Underwriting Documents"
                    items={
                      effectiveSummary?.recommended_underwriting_documents ||
                      ["No underwriting document checklist available yet."]
                    }
                    color="blue"
                  />
                </div>

                <div className="lg:col-span-2">
                  <TextCard
                    title="AI Claim Story Summary"
                    text={
                      effectiveSummary?.claim_story_summary ||
                      "No AI claim story summary available yet."
                    }
                  />
                </div>

                <div className="lg:col-span-2">
                  <ListCard
                    title="AI Claim Story Generator"
                    items={
                      Array.isArray(effectiveSummary?.ai_claim_stories) &&
                      effectiveSummary.ai_claim_stories.length > 0
                        ? effectiveSummary.ai_claim_stories.map((story: any) =>
                            typeof story === "string"
                              ? story
                              : `${story.claim_number || "Claim"} - ${
                                  story.carrier_facing_story ||
                                  story.story ||
                                  "No claim story available."
                                }`
                          )
                        : ["No AI claim stories available yet."]
                    }
                    color="purple"
                  />
                </div>
              </div>

              <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mt-6">
                <TextCard title="Broker Recommendation" text={effectiveSummary?.broker_recommendation || "Upload claims to generate a broker recommendation."} />
                <TextCard title="Renewal Summary" text={effectiveSummary?.renewal_summary || "No renewal summary available yet."} />
              </div>
            </section>
          )}

          {activeTool === "decision" && (
            <section className="glass-panel p-6 md:p-8">
              <p className="text-sm uppercase tracking-[0.25em] text-purple-300 mb-3">
                Underwriter Decision Engine
              </p>

              <h2 className="text-2xl md:text-3xl font-bold mb-6">
                Carrier Placement Intelligence
              </h2>

              <div className="grid grid-cols-1 md:grid-cols-4 gap-5 mb-8">
                <MetricCard title="Renewal Probability" value={effectiveDecision?.renewal_probability != null ? `${effectiveDecision.renewal_probability}%` : "-"} />
                <MetricCard title="Premium Impact" value={effectiveDecision?.expected_premium_impact || "-"} />
                <MetricCard title="Carrier Appetite" value={effectiveDecision?.carrier_appetite || "-"} />
                <MetricCard title="Marketability Score" value={effectiveDecision?.marketability_score != null ? `${effectiveDecision.marketability_score}/100` : "-"} />
              </div>

              <TextCard title="Submission Readiness" text={effectiveDecision?.submission_readiness || "No submission readiness available yet."} />

              <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mt-6">
                <ListCard title="Underwriting Concerns" items={effectiveDecision?.underwriting_concerns || ["No underwriting concerns available."]} color="red" />
                <ListCard title="Best Market Types" items={effectiveDecision?.best_market_types || ["No market recommendation available."]} color="purple" />
              </div>

              <div className="mt-6">
                <TextCard title="Underwriter Decision Summary" text={effectiveDecision?.underwriter_decision_summary || "No decision summary available yet."} />
              </div>
            </section>
          )}

          {activeTool === "carrier-appetite" && (
            <section className="glass-panel p-6 md:p-8">
              <p className="text-sm uppercase tracking-[0.25em] text-blue-300 mb-3">
                Carrier Appetite Engine
              </p>

              <h2 className="text-2xl md:text-3xl font-bold mb-6">
                Market Appetite Strategy
              </h2>

              <div className="grid grid-cols-1 md:grid-cols-3 gap-5 mb-8">
                <MetricCard title="Appetite Score" value={effectiveCarrierAppetite?.carrier_appetite_score != null ? `${effectiveCarrierAppetite.carrier_appetite_score}/100` : "-"} />
                <MetricCard title="Appetite Level" value={effectiveCarrierAppetite?.carrier_appetite_level || "-"} />
                <MetricCard title="Best Market" value={effectiveCarrierAppetite?.best_fit_carriers?.[0]?.carrier_type || "-"} />
              </div>

              <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                <ListCard
                  title="Best Fit Markets"
                  items={
                    effectiveCarrierAppetite?.best_fit_carriers?.length
                      ? effectiveCarrierAppetite.best_fit_carriers.map(
                          (item: any) =>
                            `${item.carrier_type} - " ${item.match_score}/100 - " ${item.fit}`
                        )
                      : ["No best fit markets available."]
                  }
                  color="blue"
                />

                <ListCard
                  title="Appetite Reasons"
                  items={effectiveCarrierAppetite?.carrier_match_reasons || ["No carrier appetite reasons available."]}
                  color="purple"
                />
              </div>

              <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mt-6">
                <TextCard
                  title="Market Strategy"
                  text={effectiveCarrierAppetite?.market_strategy || "No market strategy available yet."}
                />

                <TextCard
                  title="Placement Summary"
                  text={effectiveCarrierAppetite?.placement_summary || "No placement summary available yet."}
                />
              </div>
            </section>
          )}

          {activeTool === "submission-readiness" && (
            <section className="glass-panel p-6 md:p-8">
              <p className="text-sm uppercase tracking-[0.25em] text-green-300 mb-3">
                Submission Readiness Engine
              </p>

              <h2 className="text-2xl md:text-3xl font-bold mb-6">
                Submission Checklist & Carrier Confidence
              </h2>

              <div className="grid grid-cols-1 md:grid-cols-4 gap-5 mb-8">
                <MetricCard title="Readiness Score" value={effectiveSubmissionReadiness?.submission_readiness_score != null ? `${effectiveSubmissionReadiness.submission_readiness_score}/100` : "-"} />
                <MetricCard title="Readiness Level" value={effectiveSubmissionReadiness?.submission_readiness_level || "-"} />
                <MetricCard title="Carrier Confidence" value={effectiveSubmissionReadiness?.carrier_confidence || "-"} />
                <MetricCard title="Submission Quality" value={effectiveSubmissionReadiness?.submission_quality || "-"} />
              </div>

              <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                <ListCard
                  title="Missing Items"
                  items={effectiveSubmissionReadiness?.missing_items || ["No missing items available."]}
                  color="red"
                />

                <ListCard
                  title="Required Documents"
                  items={effectiveSubmissionReadiness?.required_documents || ["No required documents available."]}
                  color="blue"
                />
              </div>

              <div className="mt-6">
                <ListCard
                  title="Recommended Actions"
                  items={effectiveSubmissionReadiness?.recommended_actions || ["No recommended actions available."]}
                  color="purple"
                />
              </div>

              <div className="mt-6">
                <TextCard
                  title="Readiness Summary"
                  text={effectiveSubmissionReadiness?.readiness_summary || "No readiness summary available yet."}
                />
              </div>
            </section>
          )}

          {activeTool === "carrier-match" && (
  <section className="glass-panel p-6 md:p-8">
    <p className="text-sm uppercase tracking-[0.25em] text-purple-300 mb-3">
      Carrier Match Engine
    </p>

    <h2 className="text-2xl md:text-3xl font-bold mb-6">
      Named Carrier Matching
    </h2>

    <div className="grid grid-cols-1 md:grid-cols-3 gap-5 mb-8">
      <MetricCard
        title="Recommended Carrier"
        value={effectiveCarrierMatch?.recommended_carrier || "-"}
      />
      <MetricCard
        title="Match Score"
        value={
          effectiveCarrierMatch?.recommended_score != null
            ? `${effectiveCarrierMatch.recommended_score}/100`
            : "-"
        }
      />
      <MetricCard
        title="Carriers Ranked"
        value={effectiveCarrierMatch?.top_carriers?.length || 0}
      />
    </div>

    <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
      <ListCard
        title="Top Carrier Matches"
        items={
          effectiveCarrierMatch?.top_carriers?.length
            ? effectiveCarrierMatch.top_carriers.map(
                (item: any) =>
                  `${item.carrier || item.carrier_name || 'Carrier'} - " ${item.match_score ?? item.recommended_score ?? item.score ?? '-'}/100 - " ${item.fit || item.appetite || 'Market fit'}`
              )
            : ["No carrier matches available yet."]
        }
        color="purple"
      />

      <ListCard
        title="Carrier Match Reasons"
        items={
          effectiveCarrierMatch?.top_carriers?.length
            ? effectiveCarrierMatch.top_carriers.map(
                (item: any) => `${item.carrier || item.carrier_name || 'Carrier'}: ${item.reason || item.match_reason || item.fit || 'Claims data supports underwriting review.'}`
              )
            : ["No carrier match reasons available yet."]
        }
        color="blue"
      />
    </div>

    <div className="mt-6">
      <TextCard
        title="Carrier Match Summary"
        text={
          effectiveCarrierMatch?.carrier_match_summary ||
          "No carrier match summary available yet."
        }
      />
    </div>
  </section>
)}

{activeTool === "premium-forecast" &&
  (() => {
    // LOSSQ_SAFE_PREMIUM_FORECAST_REBUILD_V2
    const moneyToNumber = (value: any): number => {
      if (value === null || value === undefined) return 0;
      if (typeof value === "number") return Number.isFinite(value) ? value : 0;

      const cleaned = String(value)
        .replace(/[$,]/g, "")
        .replace(/[^0-9.-]/g, "")
        .trim();

      const parsed = Number(cleaned);
      return Number.isFinite(parsed) ? parsed : 0;
    };

    const formatMoney = (value: any) =>
      `$${Number(moneyToNumber(value) || 0).toLocaleString()}`;

    const sourceProfile: any = {
      ...(profile || {}),
      ...(displayProfile || {}),
    };

    const derivedExposure: any = deriveExposureInputsFromPolicyRows(sourceProfile);

    const currentPremium =
      moneyToNumber(sourceProfile?.current_premium) ||
      moneyToNumber(derivedExposure?.current_premium) ||
      moneyToNumber(sourceProfile?.expiring_premium) ||
      moneyToNumber(derivedExposure?.expiring_premium);

    const expiringPremium =
      moneyToNumber(sourceProfile?.expiring_premium) ||
      moneyToNumber(derivedExposure?.expiring_premium);

    const targetRenewalPremium =
      moneyToNumber(sourceProfile?.target_renewal_premium) ||
      moneyToNumber(derivedExposure?.target_renewal_premium);

    const claimRows = Array.isArray(intelligenceClaims)
      ? intelligenceClaims
      : Array.isArray(visibleClaims)
      ? visibleClaims
      : [];

    const totalIncurred = claimRows.reduce((sum: number, claim: any) => {
      return sum + getClaimIncurred(claim);
    }, 0);

    const openClaimCount = claimRows.filter((claim: any) => isOpenClaimStatus(claim)).length;
    const largeLossCount = claimRows.filter((claim: any) => getClaimIncurred(claim) >= 50000).length;
    const litigationCount = claimRows.filter((claim: any) => {
      const text = `${claim?.litigation || ""} ${claim?.litigation_status || ""} ${claim?.description || ""} ${claim?.flag || ""}`.toLowerCase();
      return text.includes("litigation") || text.includes("attorney") || text.includes("suit");
    }).length;

    const hasPremiumData = currentPremium > 0;

    const claimPressurePercent =
      hasPremiumData && claimRows.length > 0
        ? Math.min(
            45,
            Math.max(
              0,
              5 +
                openClaimCount * 3 +
                largeLossCount * 5 +
                litigationCount * 7 +
                Math.round((totalIncurred / Math.max(currentPremium, 1)) * 10)
            )
          )
        : 0;

    const expectedRenewalPremium =
      targetRenewalPremium > 0
        ? targetRenewalPremium
        : hasPremiumData
        ? Math.round(currentPremium * (1 + claimPressurePercent / 100))
        : 0;

    const expectedIncrease =
      hasPremiumData && expectedRenewalPremium > 0
        ? Math.round(((expectedRenewalPremium - currentPremium) / currentPremium) * 100)
        : 0;

    const bestCase = hasPremiumData ? Math.max(0, expectedIncrease - 5) : 0;
    const worstCase = hasPremiumData ? expectedIncrease + 10 : 0;

    const confidenceScore =
      currentPremium > 0 && targetRenewalPremium > 0
        ? 92
        : currentPremium > 0 && claimRows.length > 0
        ? 84
        : currentPremium > 0
        ? 72
        : 45;

    const confidenceLabel =
      confidenceScore >= 85
        ? "Strong"
        : confidenceScore >= 70
        ? "Good"
        : "Needs Premium Data";

    const lineText =
      Array.isArray(sourceProfile?.policies) && sourceProfile.policies.length > 0
        ? sourceProfile.policies
            .map((item: any) => item?.policy_type || item?.line_of_business || item?.coverage)
            .filter(Boolean)
            .slice(0, 6)
            .join(", ")
        : sourceProfile?.line_of_business || derivedExposure?.line_of_business || "uploaded account";

    return (
      <section className="glass-panel p-6 md:p-8">
        <p className="text-sm uppercase tracking-[0.25em] text-green-300 mb-3">
          Premium Forecast Engine
        </p>

        <h2 className="text-2xl md:text-3xl font-bold mb-6">
          Renewal Premium Projection
        </h2>

        <div className="mb-8 rounded-3xl border border-blue-400/30 bg-blue-500/10 p-5">
          <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
            <div>
              <p className="text-xs uppercase tracking-[0.25em] text-blue-300">
                Premium Accuracy Guardrail
              </p>
              <h3 className="mt-2 text-xl font-bold text-white">
                {hasPremiumData ? "File-Based Estimate" : "Premium Data Needed"}
              </h3>
              <p className="mt-2 text-sm leading-6 text-slate-300">
                {hasPremiumData
                  ? `LossQ is using actual uploaded file Exposure Inputs for ${lineText}. This forecast does not use stale modeled backend premium values.`
                  : "Current premium was not found in the uploaded file or Exposure Inputs. Add current premium to generate a renewal dollar projection."}
              </p>
            </div>

            <div className="rounded-2xl border border-white/10 bg-slate-950/70 px-5 py-4 text-center min-w-[170px]">
              <p className="text-xs uppercase tracking-[0.2em] text-slate-400">
                Pricing Confidence
              </p>
              <p className="mt-2 text-2xl font-black text-blue-200">
                {confidenceLabel}
              </p>
            </div>
          </div>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-4 gap-5 mb-8">
          <MetricCard title="Current Premium" value={hasPremiumData ? formatMoney(currentPremium) : "-"} />
          <MetricCard title="Expected Renewal" value={expectedRenewalPremium > 0 ? formatMoney(expectedRenewalPremium) : "-"} />
          <MetricCard title="Expected Increase" value={hasPremiumData ? `${expectedIncrease}%` : "-"} />
          <MetricCard title="Confidence" value={`${confidenceScore}%`} />
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-5 mb-8">
          <MetricCard title="Best Case" value={hasPremiumData ? `${bestCase}%` : "-"} />
          <MetricCard title="Likely Range" value={hasPremiumData ? `${bestCase}% to ${worstCase}%` : "-"} />
          <MetricCard title="Worst Case" value={hasPremiumData ? `${worstCase}%` : "-"} />
        </div>

        <ListCard
          title="Forecast Drivers"
          color="blue"
          items={[
            "Data source: actual uploaded file Exposure Inputs.",
            `Current premium: ${hasPremiumData ? formatMoney(currentPremium) : "not provided"}.`,
            `Expiring premium: ${expiringPremium > 0 ? formatMoney(expiringPremium) : "not provided"}.`,
            `Target renewal premium: ${targetRenewalPremium > 0 ? formatMoney(targetRenewalPremium) : "not provided"}.`,
            `${claimRows.length} account-specific claim row(s) reviewed.`,
            `${openClaimCount} open claim(s).`,
            `${largeLossCount} large loss claim(s).`,
            `${litigationCount} litigation/attorney indicator(s).`,
            `Total incurred: ${formatMoney(totalIncurred)}.`,
          ]}
        />

        <div className="mt-6">
          <TextCard
            title="Forecast Summary"
            text={
              hasPremiumData
                ? targetRenewalPremium > 0
                  ? `LossQ used the uploaded file Exposure Inputs. Current premium is ${formatMoney(
                      currentPremium
                    )} and target renewal premium is ${formatMoney(
                      targetRenewalPremium
                    )}, producing an estimated ${expectedIncrease}% renewal change.`
                  : `LossQ used the uploaded file Exposure Inputs. Current premium is ${formatMoney(
                      currentPremium
                    )}. Expected renewal is ${formatMoney(
                      expectedRenewalPremium
                    )} based on account-specific claim pressure and exposure inputs.`
                : "LossQ cannot generate a renewal dollar projection until current premium is provided in the uploaded file or Exposure Inputs."
            }
          />
        </div>
      </section>
    );
  })()}

{activeTool === "submission-builder" && (
  <section className="glass-panel p-6 md:p-8">
    <p className="text-sm uppercase tracking-[0.25em] text-blue-300 mb-3">
      Submission Builder Engine
    </p>

    <h2 className="text-2xl md:text-3xl font-bold mb-4">
      Carrier Submission Package
    </h2>

    <p className="text-slate-400 mb-6">
      Select an active carrier profile, then generate a complete underwriting submission package for that account.
    </p>

    <div className="rounded-3xl border border-white/10 bg-slate-950/60 p-5 mb-8">
      <label className="block text-sm text-blue-200 mb-2">
        Select Account / Policy
      </label>

      <div className="flex flex-col md:flex-row gap-4">
        <select
          value={profile?.policy_number || ""}
          onChange={(e) => selectAccount(e.target.value)}
          className="flex-1 rounded-2xl bg-slate-950/70 border border-white/10 px-4 py-4 text-white outline-none focus:border-blue-400 focus:ring-4 focus:ring-blue-500/20"
        >
          <option value="">Select active profile...</option>

          {profiles.map((item) => (
            <option key={item.id || item.policy_number} value={item.policy_number}>
              {(item.business_name || "Unnamed Business") +
                " - " +
                (item.carrier_name || "No Carrier") +
                " - " +
                (item.policy_number || "No Policy")}
            </option>
          ))}
        </select>

        <button
  onClick={async () => {
    if (!profile?.policy_number) {
      setMessage("Select an account/profile first.");
      return;
    }

    setMessage(`Generating submission package for ${profile.policy_number}...`);

    await loadDashboard(profile.policy_number);

    setActiveTool("submission-builder");
    setMessage(`Submission package generated for ${profile.policy_number}.`);
  }}
  className="btn-primary"
>
  Generate Package
</button>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mt-5">
        <ProfileDetail label="Insured" value={displayProfile?.business_name || "-"} />
        <ProfileDetail label="Carrier" value={lossqSafeCarrierDisplay(displayProfile)} />
        <ProfileDetail label="Policy" value={displayProfile?.policy_number || "-"} />
      </div>
    </div>

    <div className="grid grid-cols-1 md:grid-cols-4 gap-5 mb-8">
      <MetricCard title="Renewal Score" value={effectiveSummary?.renewal_score ?? "-"} />
      <MetricCard title="Risk Level" value={effectiveSummary?.renewal_risk_level || "Not Rated"} />
      <MetricCard
        title="Premium Forecast"
        value={
          effectivePremiumForecast?.expected_increase_percent != null
            ? `${effectivePremiumForecast.expected_increase_percent}%`
            : "-"
        }
      />
      <MetricCard
        title="Submission Readiness"
        value={
          effectiveSubmissionReadiness?.submission_readiness_score != null
            ? `${effectiveSubmissionReadiness.submission_readiness_score}/100`
            : "-"
        }
      />
    </div>

    <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
      <TextCard
        title="Underwriter Narrative"
        text={
          submissionBuilder?.underwriter_narrative ||
          "No underwriter narrative available yet."
        }
      />

      <TextCard
        title="Executive Summary"
        text={
          submissionBuilder?.executive_summary ||
          "No executive summary available yet."
        }
      />
    </div>

    <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mt-6">
      <TextCard
        title="Broker Marketing Memo"
        text={
          submissionBuilder?.broker_marketing_memo ||
          "No broker marketing memo available yet."
        }
      />

      <TextCard
        title="Renewal Strategy"
        text={
          submissionBuilder?.renewal_strategy ||
          "No renewal strategy available yet."
        }
      />
    </div>

    <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mt-6">
      <TextCard
        title="Carrier Appetite"
        text={
          effectiveCarrierAppetite?.placement_summary ||
          effectiveCarrierAppetite?.market_strategy ||
          "No carrier appetite summary available yet."
        }
      />

      <TextCard
        title="Premium Forecast"
        text={
          effectivePremiumForecast?.forecast_summary ||
          "No premium forecast summary available yet."
        }
      />
    </div>

    <div className="mt-6">
      <TextCard
        title="Carrier Submission Email"
        text={
          submissionBuilder?.carrier_submission_email ||
          "No carrier submission email available yet."
        }
      />
    </div>

    <div className="mt-6">
      <ListCard
        title="Loss Explanations"
        items={
          submissionBuilder?.loss_explanations?.length
            ? submissionBuilder.loss_explanations.map(
                (item: any) =>
                  `${item.claim_number} - " ${item.explanation} Broker position: ${item.broker_position}`
              )
            : ["No loss explanations available yet."]
        }
        color="purple"
      />
    </div>

    <div className="mt-8 flex flex-wrap gap-4">
      <button onClick={exportExecutiveReport} className="btn-success">
        Export Executive Report
      </button>

      <button onClick={generateCarrierPacket} className="btn-purple">
        Generate Carrier Packet
      </button>

      <button onClick={prepareCarrierEmail} className="btn-primary">
        Prepare Carrier Email
      </button>

      <button onClick={() => changeActiveTool("memo")} className="btn-secondary">
        Open Renewal Memo
      </button>
    </div>
  </section>
)}

          {activeTool === "summary" && (
            <section className="glass-panel p-6 md:p-8">
              <div className="flex flex-col gap-6 lg:flex-row lg:items-start lg:justify-between mb-8">
                <div>
                  <p className="text-sm uppercase tracking-[0.25em] text-blue-300 mb-3">
                    AI Underwriting Summary
                  </p>

                  <h2 className="text-2xl md:text-3xl font-bold">
                    Executive Account Intelligence
                  </h2>

                  <p className="text-slate-400 mt-2 max-w-3xl">
                    Full underwriting narrative using claim frequency, open claims, severity, policy schedule, carrier concerns, and saved exposure inputs.
                  </p>
                </div>

                <div className="rounded-3xl border border-white/10 bg-slate-950/70 px-8 py-6 text-center min-w-[180px]">
                  <div className="text-5xl font-black">
                    {effectiveSummary?.renewal_score ?? "-"}
                  </div>
                  <div className="text-slate-400 text-sm mt-1">Renewal Score</div>

                  <div className="mt-4 inline-flex rounded-full border border-blue-400/30 bg-blue-500/10 px-4 py-2 text-sm font-bold text-blue-200">
                    {effectiveSummary?.renewal_risk_level || effectiveSummary?.risk_level || "Not Rated"}
                  </div>
                </div>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-4 gap-5 mb-8">
                <MetricCard title="Claims Used" value={effectiveSummary?.claims_used ?? effectiveSummary?.metrics?.total_claims ?? effectiveSummary?.renewal_metrics?.total_claims ?? "-"} />
                <MetricCard title="Open Claims" value={effectiveSummary?.metrics?.open_claims ?? effectiveSummary?.renewal_metrics?.open_claims ?? "-"} />
                <MetricCard title="Total Incurred" value={effectiveSummary?.metrics?.total_incurred != null ? `$${Number(effectiveSummary.metrics.total_incurred || 0).toLocaleString()}` : effectiveSummary?.renewal_metrics?.total_incurred != null ? `$${Number(effectiveSummary.renewal_metrics.total_incurred || 0).toLocaleString()}` : "-"} />
                <MetricCard title="Submission Strength" value={effectiveSummary?.submission_strength || "-"} />
              </div>

              <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                <TextCard
                  title="Executive Summary"
                  text={
                    effectiveSummary?.renewal_summary ||
                    effectiveSummary?.summary ||
                    effectiveSummary?.carrier_narrative ||
                    "No executive summary available yet."
                  }
                />

                <TextCard
                  title="Broker Recommendation"
                  text={
                    effectiveSummary?.broker_recommendation ||
                    effectiveSummary?.recommendation ||
                    "Upload claims to generate a broker recommendation."
                  }
                />
              </div>

              <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mt-6">
                <ListCard
                  title="Renewal Drivers"
                  items={
                    Array.isArray(effectiveSummary?.renewal_drivers) && effectiveSummary.renewal_drivers.length
                      ? effectiveSummary.renewal_drivers
                      : Array.isArray(effectiveSummary?.recommended_actions) && effectiveSummary.recommended_actions.length
                      ? effectiveSummary.recommended_actions
                      : ["No renewal drivers available."]
                  }
                  color="blue"
                />

                <ListCard
                  title="Carrier Concerns"
                  items={
                    Array.isArray(effectiveSummary?.carrier_concerns) && effectiveSummary.carrier_concerns.length
                      ? effectiveSummary.carrier_concerns
                      : Array.isArray(effectiveSummary?.missing_items) && effectiveSummary.missing_items.length
                      ? effectiveSummary.missing_items
                      : ["No carrier concerns available."]
                  }
                  color="red"
                />
              </div>

              {Array.isArray(effectiveSummary?.exposure_drivers) && effectiveSummary.exposure_drivers.length > 0 && (
                <div className="mt-6">
                  <ListCard
                    title="Exposure Inputs Used"
                    items={effectiveSummary.exposure_drivers}
                    color="purple"
                  />
                </div>
              )}

              <div className="mt-6">
                <TextCard
                  title="Carrier Narrative"
                  text={
                    effectiveSummary?.carrier_narrative ||
                    effectiveSummary?.client_narrative ||
                    "No carrier narrative available yet."
                  }
                />
              </div>
            </section>
          )}

          {activeTool === "memo" && (
            <section className="glass-panel p-6 md:p-8">
              <h2 className="text-2xl md:text-3xl font-bold mb-6">AI Renewal Memo</h2>

              <div className="flex gap-4 mb-5">
                <button onClick={generateRenewalMemo} disabled={memoLoading} className="btn-purple disabled:opacity-50">
                  {memoLoading ? "Generating..." : "Generate Renewal Memo"}
                </button>

                {renewalMemo && (
                  <button onClick={copyRenewalMemo} className="btn-secondary">
                    Copy Memo
                  </button>
                )}
              </div>

              <div className="rounded-2xl border border-white/10 bg-slate-950/70 p-5 max-h-[520px] overflow-y-auto">
                <pre className="whitespace-pre-wrap text-slate-300 leading-7 text-sm">
                  {renewalMemo || "Generate a memo above."}
                </pre>
              </div>
            </section>
          )}

          {activeTool === "charts" && (
            <section className="glass-panel p-6 md:p-8">
              <h2 className="text-2xl md:text-3xl font-bold mb-3">
                Interactive Claim Development Charts
              </h2>

              <p className="text-slate-400 mb-6">
                Visualize loss trends, claim aging, severity distribution, and line-of-business concentration.
              </p>

              <div className="grid grid-cols-1 md:grid-cols-4 gap-5 mb-8">
                <MetricCard title="Reserve Pressure" value={reservePressureDisplay} />
                <MetricCard title="Open Claims" value={hasActiveAccount ? openClaims : "-"} />
                <MetricCard title="Total Reserve" value={hasActiveAccount ? `$${Number(totalReserve || 0).toLocaleString()}` : "-"} />
                <MetricCard title="Total Incurred" value={totalIncurredDisplay} />
              </div>

              <div className="mb-8 rounded-3xl border border-blue-400/20 bg-blue-500/10 p-5">
                <p className="text-sm font-semibold text-blue-200 mb-2">
                  Model Prediction View
                </p>
                <p className="text-sm text-slate-300 leading-6">
                  {modelChartNarrative}
                </p>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-8">
                <ChartCard title="Prediction Scores">
                  <ResponsiveContainer width="100%" height={300}>
                    <BarChart data={modelScoreChartData}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
                      <XAxis dataKey="name" stroke="#94a3b8" />
                      <YAxis stroke="#94a3b8" domain={[0, 100]} />
                      <Tooltip contentStyle={{ backgroundColor: "#0f172a", border: "1px solid #334155", color: "#fff" }} />
                      <Bar dataKey="value" fill="#38bdf8" radius={[8, 8, 0, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                </ChartCard>

                <ChartCard title="Premium Forecast Range">
                  <ResponsiveContainer width="100%" height={300}>
                    <BarChart data={premiumForecastRangeData}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
                      <XAxis dataKey="name" stroke="#94a3b8" />
                      <YAxis stroke="#94a3b8" />
                      <Tooltip contentStyle={{ backgroundColor: "#0f172a", border: "1px solid #334155", color: "#fff" }} />
                      <Bar dataKey="value" fill="#a78bfa" radius={[8, 8, 0, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                </ChartCard>
              </div>

              {modelLossDriverLineData.length > 0 && (
                <div className="mb-8">
                  <ChartCard title="Model Loss Drivers by Line">
                    <ResponsiveContainer width="100%" height={340}>
                      <BarChart data={modelLossDriverLineData}>
                        <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
                        <XAxis dataKey="name" stroke="#94a3b8" />
                        <YAxis stroke="#94a3b8" />
                        <Tooltip contentStyle={{ backgroundColor: "#0f172a", border: "1px solid #334155", color: "#fff" }} />
                        <Bar dataKey="incurred" fill="#38bdf8" radius={[8, 8, 0, 0]} />
                        <Bar dataKey="reserve" fill="#f59e0b" radius={[8, 8, 0, 0]} />
                        <Bar dataKey="claims" fill="#22c55e" radius={[8, 8, 0, 0]} />
                        <Bar dataKey="litigation" fill="#ef4444" radius={[8, 8, 0, 0]} />
                      </BarChart>
                    </ResponsiveContainer>
                  </ChartCard>
                </div>
              )}

              <div className="rounded-2xl border border-white/10 bg-slate-950/70 p-5 mb-6">
                <h3 className="font-semibold mb-2">Trend Intelligence</h3>
                <p className="text-slate-300">{trendNoteDisplay}</p>
              </div>

              {policySchedule.length > 0 && (
                <div className="rounded-2xl border border-white/10 bg-slate-950/70 p-5 mb-6 overflow-x-auto">
                  <h3 className="font-semibold mb-3">Policies Feeding This Analysis</h3>
                  <table className="w-full min-w-[760px] text-sm">
                    <thead>
                      <tr className="border-b border-white/10 text-left text-slate-300">
                        <th className="py-3 pr-4">Line / Coverage</th>
                        <th className="py-3 pr-4">Policy Number</th>
                        <th className="py-3 pr-4">Claims</th>
                        <th className="py-3 pr-4">Total Incurred</th>
                      </tr>
                    </thead>
                    <tbody>
                      {lossqStrictCleanPolicySchedule(policySchedule).map((policy: any, index: number) => {
                        const policyNumber = normalizePolicyNumber(policy?.policy_number);
                        const stats = scheduleClaimStats[policyNumber];
                        return (
                          <tr key={policy?.policy_number || index} className="border-b border-white/10">
                            <td className="py-3 pr-4 text-white">
                              {lossqLineOfBusinessFromObject(policy)}
                            </td>
                            <td className="py-3 pr-4 font-semibold text-blue-200">
                              {lossqPolicyNumberFromObject(policy)}
                            </td>
                            <td className="py-3 pr-4">
                              {stats?.count ?? policy?.claim_count ?? "-"}
                            </td>
                            <td className="py-3 pr-4">
                              ${Number(stats?.totalIncurred ?? policy?.total_incurred ?? 0).toLocaleString()}
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              )}

              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                <ChartCard title="Incurred Loss Trend">
                  <ResponsiveContainer width="100%" height={280}>
                    <LineChart data={lossTrendData}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
                      <XAxis dataKey="name" stroke="#94a3b8" />
                      <YAxis stroke="#94a3b8" />
                      <Tooltip contentStyle={{ backgroundColor: "#0f172a", border: "1px solid #334155", color: "#fff" }} />
                      <Line type="monotone" dataKey="value" stroke="#38bdf8" strokeWidth={4} dot={{ fill: "#38bdf8", strokeWidth: 2, r: 5 }} />
                    </LineChart>
                  </ResponsiveContainer>
                </ChartCard>

                <ChartCard title="Open Claim Aging">
                  <ResponsiveContainer width="100%" height={280}>
                    <BarChart data={agingData}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
                      <XAxis dataKey="name" stroke="#94a3b8" />
                      <YAxis stroke="#94a3b8" />
                      <Tooltip contentStyle={{ backgroundColor: "#0f172a", border: "1px solid #334155", color: "#fff" }} />
                      <Bar dataKey="value" fill="#f59e0b" radius={[8, 8, 0, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                </ChartCard>

                <ChartCard title="Severity Distribution">
                  <ResponsiveContainer width="100%" height={280}>
                    <PieChart>
                      <Pie data={severityData} dataKey="value" nameKey="name" outerRadius={100} label>
                        {severityData.map((_, index) => {
                          const colors = ["#22c55e", "#eab308", "#f97316", "#ef4444"];
                          return <Cell key={`cell-${index}`} fill={colors[index % colors.length]} />;
                        })}
                      </Pie>
                      <Tooltip contentStyle={{ backgroundColor: "#0f172a", border: "1px solid #334155", color: "#fff" }} />
                    </PieChart>
                  </ResponsiveContainer>
                </ChartCard>

                <ChartCard title="Incurred by Line of Business">
                  <ResponsiveContainer width="100%" height={280}>
                    <BarChart data={lineData}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
                      <XAxis dataKey="name" stroke="#94a3b8" />
                      <YAxis stroke="#94a3b8" />
                      <Tooltip contentStyle={{ backgroundColor: "#0f172a", border: "1px solid #334155", color: "#fff" }} />
                      <Bar dataKey="value" fill="#8b5cf6" radius={[8, 8, 0, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                </ChartCard>
              </div>
            </section>
          )}

          {activeTool === "claims" && (
            <section className="glass-panel p-6 md:p-8">
              <h2 className="text-2xl md:text-3xl font-bold mb-6">Claims Analysis</h2>

              <div className="grid grid-cols-1 md:grid-cols-4 gap-5 mb-8">
                <MetricCard title="Total Claims" value={totalClaimsDisplay} />
		<MetricCard title="Open Claims" value={openClaimsDisplay} />
		<MetricCard title="Flagged Claims" value={flaggedClaimsDisplay} />
		<MetricCard title="Total Incurred" value={totalIncurredDisplay} />
              </div>

              <div className="overflow-x-auto">
                <table className="w-full min-w-[900px]">
                  <thead>
                    <tr className="border-b border-white/10 text-left text-slate-300">
                      {[
                        ["claim_number", "Claim #"],
                        ["line", "Line"],
                        ["status", "Status"],
                        ["paid", "Paid"],
                        ["reserve", "Reserve"],
                        ["total", "Total"],
                        ["policy", "Policy"],
                        ["flag", "Flag"],
                      ].map(([key, label]) => (
                        <th key={key} className="pb-4">
                          <button
                            type="button"
                            onClick={() =>
                              setClaimAnalysisSort((current) => ({
                                key,
                                direction:
                                  current.key === key && current.direction === "asc"
                                    ? "desc"
                                    : "asc",
                              }))
                            }
                            className="inline-flex items-center gap-2 text-left text-slate-300 hover:text-white"
                            title={`Sort by ${label}`}
                          >
                            <span>{label}</span>
                            <span className="text-xs text-blue-300">
                              {claimAnalysisSort.key === key
                                ? claimAnalysisSort.direction === "asc"
                                  ? String.fromCharCode(9650)
                                  : String.fromCharCode(9660)
                                : String.fromCharCode(8597)}
                            </span>
                          </button>
                        </th>
                      ))}
                    </tr>
                  </thead>

<tbody>
  {visibleClaims.length === 0 && (
    <tr className="border-b border-white/10 text-slate-400">
      <td className="py-6 text-center" colSpan={8}>
        No claims found for the selected account. Upload or select another account to view claim-level detail.
      </td>
    </tr>
  )}

  {[...groupedVisibleClaims]
    .sort((a: any, b: any) => {
      const moneyValue = (value: any) => {
        const cleaned = String(value || "").replace(/[^0-9.-]/g, "");
        const parsed = Number(cleaned);
        return Number.isFinite(parsed) ? parsed : 0;
      };

      const textValue = (value: any) => String(value || "").trim().toLowerCase();

      const claimSortValue = (claim: any) => {
        const paid = moneyValue(claim?.paid_amount || claim?.paid || claim?.paidAmount);
        const reserve = moneyValue(claim?.reserve_amount || claim?.reserve || claim?.reserveAmount);
        const total = Number(getClaimIncurred(claim) || paid + reserve || 0);

        switch (claimAnalysisSort.key) {
          case "claim_number":
            return textValue(claim?.claim_number || claim?.claimNumber || claim?.claim_no);
          case "line":
            return textValue(claim?.line_of_business || claim?.line || claim?.coverage || claim?.lob);
          case "status":
            return textValue(claim?.status);
          case "paid":
            return paid;
          case "reserve":
            return reserve;
          case "total":
            return total;
          case "policy":
            return textValue(claim?.policy_number || claim?.policy || claim?.policyNumber);
          case "flag":
            return textValue(claim?.flag);
          default:
            return total;
        }
      };

      const av = claimSortValue(a);
      const bv = claimSortValue(b);

      let comparison = 0;

      if (typeof av === "number" && typeof bv === "number") {
        comparison = av - bv;
      } else {
        comparison = String(av).localeCompare(String(bv), undefined, {
          numeric: true,
          sensitivity: "base",
        });
      }

      return claimAnalysisSort.direction === "asc" ? comparison : -comparison;
    })
    .map((claim: any) => {
      const cleanPolicyKey = (value: any) =>
        String(value || "").toUpperCase().replace(/[^A-Z0-9]/g, "");

      const policyFamilyTokens = (policyNumber: any) =>
        String(policyNumber || "")
          .toUpperCase()
          .split(/[^A-Z0-9]+/)
          .filter((token) => /[A-Z]/.test(token) && token.length >= 2);

      const getPolicyNumber = (item: any) =>
        String(
          item?.policy_number ||
            item?.policyNumber ||
            item?.policy_no ||
            item?.policy ||
            ""
        ).trim();

      const getPolicyLine = (item: any) =>
        String(
          item?.line_of_business ||
            item?.policy_type ||
            item?.line_coverage ||
            item?.coverage ||
            item?.line ||
            item?.lob ||
            ""
        ).trim();

      const isGenericLine = (value: any) => {
        const clean = String(value || "").trim().toLowerCase();
        return !clean || ["policy", "policies", "coverage", "line", "unknown", "n/a", "none", "-"].includes(clean);
      };

      const claimNumberText = String(
        claim?.claim_number || claim?.claimNumber || claim?.claim_no || ""
      ).toUpperCase();

      const claimPolicyKey = cleanPolicyKey(
        claim?.policy_number || claim?.policy || claim?.policyNumber || claim?.policy_no
      );

      const policyCandidates = (policySchedule || [])
        .map((policy: any) => {
          const policyNumber = getPolicyNumber(policy);
          const line = getPolicyLine(policy);

          return {
            policy,
            policyNumber,
            line,
            policyKey: cleanPolicyKey(policyNumber),
            tokens: policyFamilyTokens(policyNumber),
          };
        })
        .filter((item: any) => item.policyKey || item.line);

      const matchedPolicy =
        policyCandidates.find((item: any) =>
          item.tokens.some((token: string) =>
            new RegExp(`(^|[^A-Z0-9])${token}([^A-Z0-9]|$)`).test(claimNumberText)
          )
        ) ||
        policyCandidates.find((item: any) => item.policyKey && item.policyKey === claimPolicyKey) ||
        policyCandidates.find((item: any) =>
          item.policyKey &&
          claimPolicyKey &&
          (item.policyKey.includes(claimPolicyKey) || claimPolicyKey.includes(item.policyKey))
        );

      const originalClaimLine =
        claim?.line_of_business || claim?.claim_type || claim?.line || claim?.coverage || claim?.lob || "";

      // LOSSQ_CLAIM_TABLE_ROW_FIRST_DISPLAY_V1
      const displayLine =
        !isGenericLine(originalClaimLine)
          ? originalClaimLine
          : matchedPolicy?.line && !isGenericLine(matchedPolicy.line)
            ? matchedPolicy.line
            : "-";

      const displayPolicyNumber =
        claim?.policy_number ||
        claim?.policyNumber ||
        claim?.policy_no ||
        claim?.policy ||
        matchedPolicy?.policyNumber ||
        "-";
      return (
    <tr
      key={claim.id || claim.claim_number}
      className="border-b border-white/10 text-slate-300"
    >
      <td className="py-4">
        <button
          type="button"
          onClick={() => openClaimRecord(claim)}
          className="text-left text-blue-300 hover:text-blue-200 underline"
        >
          {claim.claim_number || "Unnamed Claim"}
        </button>
      </td>

      <td>{displayLine}</td>
      <td>{claim.status || "-"}</td>
      <td>${Number(claim.paid_amount || claim.paid || 0).toLocaleString()}</td>
      <td>${Number(claim.reserve_amount || claim.reserve || 0).toLocaleString()}</td>
      <td>${Number(getClaimIncurred(claim)).toLocaleString()}</td>
      <td>{displayPolicyNumber}</td>

      <td>
        {claim.flag ? (
          <span className="text-red-300">{claim.flag}</span>
        ) : (
          <span className="text-slate-500">None</span>
        )}
      </td>
    </tr>
      );
    })}
</tbody>
</table>
</div>

{selectedClaimDetail && (
  <div className="mt-6 rounded-2xl border border-blue-400/20 bg-blue-500/10 p-5">
    <div className="flex items-start justify-between gap-4">
      <div>
        <p className="text-xs uppercase tracking-[0.25em] text-blue-200">Claim Detail Preview</p>
        <h3 className="mt-2 text-xl font-bold text-white">{selectedClaimDetail.claim_number || "Unnamed Claim"}</h3>
      </div>
      <button
        type="button"
        onClick={() => setSelectedClaimDetail(null)}
        className="rounded-lg border border-white/10 px-3 py-2 text-sm text-slate-300 hover:bg-white/10"
      >
        Close
      </button>
    </div>

    <div className="mt-4 grid grid-cols-1 md:grid-cols-4 gap-3 text-sm">
      {[
        ["Policy", selectedClaimDetail.policy_number || "-"],
        ["Line", selectedClaimDetail.line_of_business || selectedClaimDetail.claim_type || "-"],
        ["Status", selectedClaimDetail.status || "-"],
        ["Total", `$${Number(getClaimIncurred(selectedClaimDetail)).toLocaleString()}`],
      ].map(([label, value]) => (
        <div key={label} className="rounded-xl border border-white/10 bg-slate-950/70 p-3">
          <p className="text-[10px] uppercase tracking-[0.2em] text-slate-500">{label}</p>
          <p className="mt-1 font-semibold text-white">{value}</p>
        </div>
      ))}
    </div>

    <p className="mt-4 text-slate-300">
      {selectedClaimDetail.description || "No description available."}
    </p>
  </div>
)}
</section>
)}
</section>
</div>

<button

        onClick={() => setCopilotOpen(!copilotOpen)}
        className="fixed bottom-6 right-6 z-50 rounded-full bg-blue-600 hover:bg-blue-500 px-6 py-4 font-semibold shadow-2xl shadow-blue-600/40"
      >
        {copilotOpen ? "Close Copilot" : "Ask Copilot"}
      </button>

      {copilotOpen && (
        <div className="fixed bottom-24 right-6 z-50 w-[420px] max-w-[calc(100vw-3rem)] bg-slate-950/95 backdrop-blur-xl border border-blue-400/30 rounded-3xl shadow-2xl shadow-blue-900/40 overflow-hidden">
          <div className="bg-white/5 px-5 py-4 flex justify-between border-b border-white/10">
            <div>
              <h2 className="font-semibold">AI Underwriting Copilot</h2>
              <p className="text-xs text-slate-400">
                 Account: {getAccountDisplayName(profile) || "No account selected"} | Policy: {displayProfile?.policy_number || "N/A"}
              </p>
            </div>

            <button onClick={() => setCopilotOpen(false)} className="text-slate-400 hover:text-white">
              Close
            </button>
          </div>

          <div className="p-5 max-h-[520px] overflow-y-auto">
            {[
              "What are the biggest renewal concerns?",
              "Summarize litigation exposure.",
              "What claims should concern carriers?",
              "What should the broker explain before submission?",
            ].map((q) => (
              <button
                key={q}
                onClick={() => askCopilot(q)}
                className="w-full text-left bg-white/5 hover:bg-white/10 border border-white/10 rounded-xl px-3 py-2 text-sm mb-2"
              >
                {q}
              </button>
            ))}

            <div className="flex gap-2 mt-4">
              <input
                value={copilotQuestion}
                onChange={(e) => setCopilotQuestion(e.target.value)}
                placeholder="Ask a question..."
                className="flex-1 bg-slate-950 border border-white/10 rounded-xl px-3 py-2 text-sm outline-none focus:border-blue-400"
              />

              <button onClick={() => askCopilot()} disabled={copilotLoading} className="btn-primary disabled:opacity-50">
                {copilotLoading ? "..." : "Ask"}
              </button>
            </div>

            {copilotAnswer && (
              <div className="bg-white/5 border border-white/10 rounded-2xl p-4 mt-4">
                <p className="text-slate-300 whitespace-pre-line text-sm leading-7">
                  {copilotAnswer}
                </p>
              </div>
            )}
          </div>
        </div>
      )}

      <style jsx global>{`
        .glass-panel {
          border-radius: 1.5rem;
          border: 1px solid rgba(255, 255, 255, 0.1);
          background: rgba(15, 23, 42, 0.68);
          backdrop-filter: blur(18px);
          box-shadow: 0 24px 80px rgba(2, 6, 23, 0.45);
        }

        .btn-primary {
          border-radius: 0.9rem;
          background: linear-gradient(135deg, #2563eb, #0ea5e9);
          padding: 0.75rem 1.15rem;
          font-weight: 700;
          color: white;
          box-shadow: 0 14px 35px rgba(37, 99, 235, 0.25);
          transition: 0.2s ease;
        }

        .btn-primary:hover {
          transform: translateY(-1px);
          filter: brightness(1.08);
        }

        .btn-secondary {
          border-radius: 0.9rem;
          border: 1px solid rgba(255, 255, 255, 0.12);
          background: rgba(255, 255, 255, 0.07);
          padding: 0.75rem 1.15rem;
          font-weight: 700;
          color: white;
          transition: 0.2s ease;
        }

        .btn-secondary:hover {
          background: rgba(255, 255, 255, 0.12);
        }

        .btn-success {
          border-radius: 0.9rem;
          background: linear-gradient(135deg, #059669, #22c55e);
          padding: 0.75rem 1.15rem;
          font-weight: 700;
          color: white;
          box-shadow: 0 14px 35px rgba(34, 197, 94, 0.2);
        }

        .btn-purple {
          border-radius: 0.9rem;
          background: linear-gradient(135deg, #7c3aed, #a855f7);
          padding: 0.75rem 1.15rem;
          font-weight: 700;
          color: white;
          box-shadow: 0 14px 35px rgba(168, 85, 247, 0.2);
        }

        .btn-danger {
          border-radius: 0.9rem;
          background: linear-gradient(135deg, #dc2626, #f43f5e);
          padding: 0.75rem 1.15rem;
          font-weight: 700;
          color: white;
          box-shadow: 0 14px 35px rgba(244, 63, 94, 0.2);
        }
      `}</style>
    </main>
  );
}

function LoadingScreen({ title, subtitle }: { title: string; subtitle: string }) {
  return (
    <main className="min-h-screen bg-[#020617] text-white flex items-center justify-center px-6">
      <div className="absolute inset-0 bg-[radial-gradient(circle_at_top,#1d4ed866,transparent_35%)]" />
      <div className="relative text-center rounded-3xl border border-white/10 bg-white/10 backdrop-blur-xl p-10 shadow-2xl">
        <div className="mx-auto mb-5 h-12 w-12 rounded-full border-4 border-blue-400/30 border-t-blue-400 animate-spin" />
        <div className="text-3xl font-bold mb-3">{title}</div>
        <div className="text-slate-400">{subtitle}</div>
      </div>
    </main>
  );
}

function NavButton({ href, children }: { href: string; children: ReactNode }) {
  return (
    <a href={href} className="btn-secondary block text-center">
      {children}
    </a>
  );
}

function ToolButton({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: ReactNode;
}) {
  return (
    <button
      onClick={onClick}
      className={`mb-2 rounded-2xl px-4 py-3 text-left font-semibold transition ${
        active
          ? "bg-blue-600 text-white shadow-lg shadow-blue-600/20"
          : "text-slate-300 hover:bg-white/10 hover:text-white"
      }`}
    >
      {children}
    </button>
  );
}

function MobileToolButton({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: ReactNode;
}) {
  return (
    <button
      onClick={onClick}
      className={`rounded-xl px-4 py-2 text-sm font-semibold whitespace-nowrap ${
        active ? "bg-blue-600 text-white" : "bg-white/10 text-slate-300"
      }`}
    >
      {children}
    </button>
  );
}

function ProfileDetail({ label, value }: { label: string; value: any }) {
  return (
    <div className="rounded-2xl border border-white/10 bg-slate-950/60 p-4">
      <div className="text-xs uppercase tracking-[0.2em] text-blue-300 mb-2">{label}</div>
      <div className="font-bold break-words">{value || "-"}</div>
    </div>
  );
}

function Input({
  label,
  value,
  onChange,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
}) {
  return (
    <div>
      <label className="block text-sm text-blue-200 mb-2">{label}</label>
      <input
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="w-full bg-slate-950/70 border border-white/10 rounded-2xl px-4 py-3 outline-none focus:border-blue-400 focus:ring-4 focus:ring-blue-500/20"
      />
    </div>
  );
}

function MetricCard({ title, value }: { title: string; value: any }) {
  return (
    <div className="rounded-3xl border border-white/10 bg-white/[0.07] backdrop-blur-xl p-6 shadow-2xl shadow-slate-950/30">
      <div className="text-slate-400 mb-3 text-sm">{title}</div>
      <div className="text-2xl font-black break-words">{value || "-"}</div>
    </div>
  );
}

function TextCard({ title, text }: { title: string; text: string }) {
  return (
    <div className="rounded-3xl border border-white/10 bg-slate-950/60 p-5">
      <h3 className="font-bold text-lg mb-3">{title}</h3>
      <p className="text-slate-300 leading-7">{text}</p>
    </div>
  );
}

function ListCard({
  title,
  items,
  color,
}: {
  title: string;
  items: string[];
  color: "blue" | "red" | "purple";
}) {
  const dot =
    color === "red"
      ? "bg-red-400"
      : color === "purple"
      ? "bg-purple-400"
      : "bg-blue-400";

  return (
    <div className="rounded-3xl border border-white/10 bg-white/[0.05] p-5">
      <h3 className="font-bold text-lg mb-4">{title}</h3>
      <ul className="space-y-3 text-slate-300">
        {items.map((item: string, index: number) => (
          <li key={index} className="flex gap-3">
            <span className={`mt-2 h-2 w-2 rounded-full ${dot}`} />
            <span>{item}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

function ChartCard({
  title,
  children,
}: {
  title: string;
  children: ReactNode;
}) {
  return (
    <div className="rounded-3xl border border-white/10 bg-slate-950/60 p-5">
      <h3 className="font-bold mb-4">{title}</h3>
      {children}
    </div>
  );
}
