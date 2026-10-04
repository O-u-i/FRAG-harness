import { createHash } from "node:crypto";
import { lstat, readFile, readdir } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.dirname(fileURLToPath(import.meta.url));
const expectedManifestSha256 = "378bb2d79b440bbba3a77c9c24de0a4de4335419bbce9f4edd68ca4e348c88dd";
const expectedPiCommit = "a13d35a742c6ef8462812a28fbe1d8c8b7431c32";
const hash = (bytes) => createHash("sha256").update(bytes).digest("hex");

function requireEqual(actual, expected, code) {
  if (actual !== expected) throw new Error(code);
}

async function safePath(relative) {
  const resolved = path.resolve(root, relative);
  if (resolved === root || !resolved.startsWith(`${root}${path.sep}`)) {
    throw new Error("package_path_outside_worker");
  }
  const parts = path.relative(root, resolved).split(path.sep);
  let current = root;
  for (const part of parts) {
    current = path.join(current, part);
    if ((await lstat(current)).isSymbolicLink()) {
      throw new Error("package_symlink_refused");
    }
  }
  return resolved;
}

async function bytes(relative) {
  const resolved = await safePath(relative);
  if (!(await lstat(resolved)).isFile()) throw new Error("package_file_expected");
  return readFile(resolved);
}

async function walk(relative) {
  const resolved = await safePath(relative);
  const output = [];
  for (const item of await readdir(resolved, { withFileTypes: true })) {
    const child = `${relative}/${item.name}`;
    if (item.isSymbolicLink()) throw new Error("package_symlink_refused");
    if (item.isDirectory()) output.push(...await walk(child));
    else if (item.isFile()) output.push(child);
    else throw new Error("package_regular_entry_expected");
  }
  return output.sort();
}

async function verifyPackageContents(installed) {
  const manifestBytes = await bytes("vendor/pi-ai/selection-manifest.json");
  requireEqual(hash(manifestBytes), expectedManifestSha256, "selection_manifest_changed");
  const manifest = JSON.parse(manifestBytes.toString("utf8"));
  requireEqual(manifest.version, "1.0.0", "pi_version_changed");
  requireEqual(manifest.officialCommit, expectedPiCommit, "pi_source_changed");
  requireEqual(manifest.files.length, 29, "pi_file_count_changed");
  for (const entry of manifest.files) {
    const content = await bytes(`vendor/pi-ai/${entry.path}`);
    requireEqual(hash(content), entry.sha256, "pi_selected_file_changed");
    requireEqual(content.length, entry.bytes, "pi_selected_file_size_changed");
  }
  const actualPiFiles = await walk("vendor/pi-ai/dist");
  const expectedPiFiles = manifest.files.map((entry) => `vendor/pi-ai/${entry.path}`).sort();
  requireEqual(JSON.stringify(actualPiFiles), JSON.stringify(expectedPiFiles), "pi_unreviewed_file");
  requireEqual(manifest.legalDocuments.length, 6, "legal_document_count_changed");
  for (const document of manifest.legalDocuments) {
    requireEqual(hash(await bytes(document.path)), document.sha256, "original_legal_document_changed");
  }

  const packageJson = JSON.parse((await bytes("package.json")).toString("utf8"));
  const expectedDependencies = { openai: "7.19.0", "partial-json": "0.1.7" };
  requireEqual(JSON.stringify(packageJson.dependencies), JSON.stringify(expectedDependencies), "worker_dependencies_changed");
  requireEqual(packageJson.private, true, "worker_private_required");
  requireEqual(packageJson.type, "module", "worker_module_required");
  if (Object.keys(packageJson.optionalDependencies ?? {}).length ||
      Object.keys(packageJson.devDependencies ?? {}).length ||
      Object.keys(packageJson.peerDependencies ?? {}).length) {
    throw new Error("worker_unreviewed_dependencies");
  }
  if (!installed) {
    return {
      status: "PASS",
      scope: "source_and_original_notices_only",
      selectedPiFiles: 29,
      originalLegalDocuments: 6,
      installStatus: "NOT_CHECKED",
      manifestSha256: expectedManifestSha256,
    };
  }
  const lock = JSON.parse((await bytes("package-lock.json")).toString("utf8"));
  requireEqual(lock.lockfileVersion, 3, "worker_lock_version_changed");
  requireEqual(JSON.stringify(lock.packages[""].dependencies), JSON.stringify(expectedDependencies), "worker_lock_dependencies_changed");
  requireEqual(JSON.stringify(Object.keys(lock.packages).sort()),
    JSON.stringify(["", "node_modules/openai", "node_modules/partial-json"]),
    "worker_lock_unreviewed_package");
  const installedEntries = (await readdir(await safePath("node_modules"))).sort();
  for (const entry of installedEntries) {
    if (![".bin", ".package-lock.json", "openai", "partial-json"].includes(entry)) {
      throw new Error("worker_installed_unreviewed_package");
    }
  }
  let installedFiles = 0;
  for (const pin of manifest.externalPackages) {
    const locked = lock.packages[`node_modules/${pin.name}`];
    requireEqual(locked.version, pin.version, "worker_locked_version_changed");
    requireEqual(locked.integrity, pin.integrity, "worker_locked_integrity_changed");
    requireEqual(locked.resolved, pin.tarball, "worker_locked_origin_changed");
    const base = `node_modules/${pin.name}`;
    const installed = JSON.parse((await bytes(`${base}/package.json`)).toString("utf8"));
    requireEqual(installed.name, pin.name, "worker_installed_name_changed");
    requireEqual(installed.version, pin.version, "worker_installed_version_changed");
    const files = await walk(base);
    requireEqual(files.length, pin.fileCount, "worker_installed_file_count_changed");
    const digestInput = [];
    for (const file of files) {
      digestInput.push(`${file.slice(base.length + 1)}\0${hash(await bytes(file))}\n`);
    }
    requireEqual(hash(Buffer.from(digestInput.join(""))), pin.filesSha256, "worker_installed_bytes_changed");
    installedFiles += files.length;
  }
  return {
    status: "PASS",
    selectedPiFiles: 29,
    originalLegalDocuments: 6,
    installedPackages: 2,
    installedFiles,
    optionalPeersInstalled: false,
    manifestSha256: expectedManifestSha256,
  };
}

export async function verifyPackage({ installed = true } = {}) {
  try {
    if (typeof installed !== "boolean") throw new Error("package_verification_options_invalid");
    return await verifyPackageContents(installed);
  } catch (error) {
    const code = error instanceof Error && /^[a-z_]+$/.test(error.message)
      ? error.message : "package_verification_failed";
    throw new Error(code);
  }
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  try {
    process.stdout.write(`${JSON.stringify(await verifyPackage())}\n`);
  } catch (error) {
    const code = error instanceof Error && /^[a-z_]+$/.test(error.message)
      ? error.message : "package_verification_failed";
    process.stderr.write(`${code}\n`);
    process.exitCode = 1;
  }
}
