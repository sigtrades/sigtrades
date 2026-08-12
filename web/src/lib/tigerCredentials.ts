export type TigerCredentialPayload = {
  account_id: string;
  private_key: string;
  config: Record<string, unknown>;
  /** TBHK 等牌照所需；写入 secrets_encrypted */
  secrets?: { token: string };
};

export type TigerParsedFile = {
  tiger_id?: string;
  account?: string;
  license?: string;
  env?: string;
  private_key?: string;
  /** tiger_openapi_token.properties 或主配置内的 token= */
  token?: string;
  source: "properties" | "keyfile" | "tokenfile";
  filename: string;
};

/** 需要 Authorization user token 的牌照（与 TBNZ 相对） */
export function tigerLicenseRequiresToken(license?: string | null): boolean {
  return (license || "").trim().toUpperCase() === "TBHK";
}

function parsePropertiesContent(text: string): Record<string, string> {
  const out: Record<string, string> = {};
  for (const rawLine of text.split(/\r?\n/)) {
    const line = rawLine.trim();
    if (!line || line.startsWith("#")) continue;
    const idx = line.indexOf("=");
    if (idx <= 0) continue;
    const key = line.slice(0, idx).trim();
    const value = line.slice(idx + 1).trim();
    out[key] = value;
  }
  return out;
}

function normalizePrivateKey(raw: string): string {
  const trimmed = raw.trim();
  if (trimmed.includes("BEGIN")) return trimmed;
  // pk8/pk1 one-line base64 from properties file
  return trimmed;
}

function isKeyFile(name: string, content: string): boolean {
  const lower = name.toLowerCase();
  if (/\.(pem|key|pk8|pk1|txt)$/.test(lower)) return true;
  return content.includes("BEGIN") && content.includes("PRIVATE KEY");
}

function isTokenPropertiesFile(filename: string, props: Record<string, string>): boolean {
  const lower = filename.toLowerCase();
  if (lower.includes("token") && props.token) return true;
  const keys = Object.keys(props);
  return Boolean(props.token) && !props.private_key_pk1 && !props.private_key_pk8 && !props.private_key && !props.tiger_id;
}

export function parseTigerCredentialFile(filename: string, content: string): TigerParsedFile {
  const trimmed = content.trim();
  const lower = filename.toLowerCase();

  if (lower.endsWith(".properties") || trimmed.includes("tiger_id=") || trimmed.includes("private_key") || trimmed.includes("token=")) {
    const props = parsePropertiesContent(trimmed);
    if (isTokenPropertiesFile(filename, props)) {
      return {
        source: "tokenfile",
        filename,
        token: props.token?.trim() || undefined,
        license: props.license?.trim() || undefined,
      };
    }
    // 统一优先 private_key_pk1（与老虎开发者后台 / 线上策略一致）；无 pk1 时再回退 pk8
    const private_key =
      props.private_key_pk1 ||
      props.private_key_pk8 ||
      props.private_key ||
      props.privateKey;
    return {
      source: "properties",
      filename,
      tiger_id: props.tiger_id || props.tigerId,
      account: props.account || props.defaultAccount,
      license: props.license,
      env: props.env,
      token: props.token?.trim() || undefined,
      private_key: private_key ? normalizePrivateKey(private_key) : undefined,
    };
  }

  if (isKeyFile(filename, trimmed)) {
    return {
      source: "keyfile",
      filename,
      private_key: normalizePrivateKey(trimmed),
    };
  }

  throw new Error("unsupported tiger credential file");
}

/** 合并主配置与 token 文件（后上传的覆盖对应字段）。 */
export function mergeTigerParsedFiles(
  base: TigerParsedFile | null,
  next: TigerParsedFile,
): TigerParsedFile {
  if (!base) return next;
  if (next.source === "tokenfile") {
    return {
      ...base,
      token: next.token || base.token,
      license: next.license || base.license,
      filename: base.private_key ? `${base.filename}+${next.filename}` : next.filename,
    };
  }
  return {
    ...base,
    ...next,
    token: next.token || base.token,
    license: next.license || base.license,
    private_key: next.private_key || base.private_key,
    tiger_id: next.tiger_id || base.tiger_id,
    account: next.account || base.account,
    env: next.env || base.env,
    filename: next.private_key ? next.filename : base.filename,
  };
}

export function buildTigerCredentialPayload(
  parsed: TigerParsedFile,
  manual: {
    tiger_id?: string;
    account_id?: string;
    env?: "test" | "production" | "paper" | "live";
    token?: string;
    license?: string;
  },
): TigerCredentialPayload {
  const tiger_id = manual.tiger_id?.trim() || parsed.tiger_id?.trim();
  const account_id = manual.account_id?.trim() || parsed.account?.trim() || "";
  const private_key = parsed.private_key?.trim();
  const license = (manual.license || parsed.license || "TBNZ").trim().toUpperCase() || "TBNZ";
  const token = (manual.token || parsed.token || "").trim();

  if (!private_key) {
    throw new Error("private key missing");
  }
  if (!tiger_id) {
    throw new Error("tiger id missing");
  }
  if (!account_id) {
    throw new Error("account missing");
  }
  if (tigerLicenseRequiresToken(license) && !token) {
    throw new Error("TBHK license requires token");
  }

  // 老虎模拟/正式只做标识；API 一律走正式网关，模拟盘由 ≥17 位账号区分
  const paperByAccount = /^\d{17,}$/.test(account_id);
  const mode: "paper" | "live" = paperByAccount
    ? "paper"
    : manual.env === "test" || manual.env === "paper"
      ? "paper"
      : "live";

  const config: Record<string, unknown> = {
    env: mode,
    sandbox: false,
    license,
    tiger_id,
    account: account_id,
    production: { tiger_id, account: account_id },
  };

  const payload: TigerCredentialPayload = {
    account_id,
    private_key,
    config,
  };
  if (token) {
    payload.secrets = { token };
  }
  return payload;
}
