/**
 * Shared secret/credential filename denylist — the SINGLE source of truth for:
 *   - protect-secrets.mjs   (PreToolUse Write|Edit: block editing a secret file)
 *   - auto-commit.mjs       (Stop: exclude secret files from staging before commit/push)
 *   - guard-bash.mjs        (PreToolUse Bash|PowerShell: block shell overwrite/read of secrets)
 *
 * Keeping all three on one list closes the coverage-divergence gap (a file blocked on
 * write but readable, committed, or pushed) without re-maintaining the patterns in N places.
 *
 * `isSecretFile(pathLike)` -> boolean.
 *   - Templates (`.example`/`.sample`/`.template`/`.dist`) are NEVER secret.
 *   - Ordinary SOURCE files that merely contain "secret"/"credential" in the name
 *     (e.g. `secret_manager.py`, `test_secrets.ts`) are NOT blocked — only credential-SHAPED
 *     files are. This avoids the old over-block where any `*secret*.py` (incl. this hook's own
 *     siblings) became un-editable.
 */

const TEMPLATE_RE = /\.(example|sample|template|dist)$/;

// Source/code extensions that should pass even when the name carries a secret token.
const CODE_EXT_RE =
  /\.(py|pyi|ts|tsx|js|jsx|mjs|cjs|md|rs|go|java|kt|rb|sh|ps1|psm1|css|scss|less|html?|vue|svelte|c|h|cc|cpp|hpp|cs|php|swift)$/;

export function baseName(pathLike) {
  return (
    String(pathLike || "")
      .replace(/\\/g, "/")
      .toLowerCase()
      .split("/")
      .pop() || ""
  );
}

export function isTemplate(base) {
  return TEMPLATE_RE.test(base);
}

/** True when `pathLike` names an actual secret/credential/key file (not a template, not source). */
export function isSecretFile(pathLike) {
  const norm = String(pathLike || "").replace(/\\/g, "/").toLowerCase();
  const base = norm.split("/").pop() || "";
  if (!base || isTemplate(base)) return false;

  const stem = base.replace(/\.[^.]+$/, "");

  // 1) .env (dotfile) and .env.<anything> AND <name>.env (e.g. prod.env / staging.env).
  //    (.env.example / *.env.example already excluded by isTemplate above.)
  if (base === ".env" || /^\.env(\.|$)/.test(base) || /\.env$/.test(base)) return true;

  // 2) key / cert / keystore material
  if (/\.(pem|key|pfx|p12|p8|jks|keystore|asc|gpg|ppk)$/.test(base)) return true;

  // 3) ssh / pgp private keys
  if (/(^|\/)id_(rsa|dsa|ecdsa|ed25519)(\.|$)/.test(base)) return true;

  // 4) well-known credential dotfiles / bare names
  if ([".npmrc", ".git-credentials", ".pgpass", ".netrc", ".pypirc", ".dockercfg"].includes(base))
    return true;

  // 5) credential/secret config files (regardless of .json/.yaml/.toml extension), but NOT
  //    source code: a bare-stem `secrets.json`/`credentials.yaml` is a secret, while `secrets.py`/
  //    `secret.ts`/`credentials.js` is source (the CODE_EXT carve-out must run BEFORE this rule).
  if (/(^|\/)\.credentials\.json$/.test(norm)) return true;
  if (/^(secret|secrets|credential|credentials|creds)$/.test(stem) && !CODE_EXT_RE.test(base))
    return true; // secrets.json, credentials.yaml — but not secrets.py
  if (/service[-_]?account.*\.json$/.test(base)) return true;
  if (/(^|[-_.])(gcp|aws|azure|firebase)[-_.].*\.json$/.test(base)) return true;
  if (/[-_]key\.json$/.test(base)) return true;

  // 6) other NON-SOURCE files whose name carries a secret token
  //    (blocks secret.env / app.credentials / .secrets ; ALLOWS secret_manager.py / test_secrets.ts)
  if (
    /(^|[._-])(secret|secrets|credential|credentials)([._-]|$)/.test(base) &&
    !CODE_EXT_RE.test(base)
  ) {
    return true;
  }

  return false;
}

/** Variant for shell tokens: strip surrounding quotes / a leading `./` before testing. */
export function isSecretTarget(token) {
  const cleaned = String(token || "")
    .replace(/^['"]+|['"]+$/g, "")
    .replace(/^\.\//, "");
  return isSecretFile(cleaned);
}
