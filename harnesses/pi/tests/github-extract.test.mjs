import assert from "node:assert/strict";
import { chmodSync, existsSync, mkdirSync, mkdtempSync, writeFileSync } from "node:fs";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { createJiti } from "jiti";

// The extension reads its config path at import and resolves gh/git from PATH
// at call time, so the sandbox must exist before the import. The stub `gh`
// fails (forcing the plain git path); the stub `git` fails unless
// STUB_GIT_README names a file for the cloned README.md to symlink to.
const sandbox = mkdtempSync(path.join(os.tmpdir(), "pi-github-extract-"));
const cloneRoot = path.join(sandbox, "clones");
const bin = path.join(sandbox, "bin");
mkdirSync(bin);
writeFileSync(
  path.join(sandbox, "web-search.json"),
  JSON.stringify({ githubClone: { clonePath: cloneRoot } }),
);
writeFileSync(path.join(bin, "gh"), "#!/bin/sh\nexit 1\n");
writeFileSync(
  path.join(bin, "git"),
  '#!/bin/sh\n[ -n "$STUB_GIT_README" ] || exit 1\n' +
    'for dest; do :; done\nmkdir -p "$dest" && ln -s "$STUB_GIT_README" "$dest/README.md"\n',
);
chmodSync(path.join(bin, "gh"), 0o755);
chmodSync(path.join(bin, "git"), 0o755);
process.env.PI_CODING_AGENT_DIR = sandbox;
process.env.PATH = `${bin}:${process.env.PATH}`;

const jiti = createJiti(import.meta.url, { tryNative: false });
const { extractGitHub, parseGitHubUrl } = await jiti.import(
  "../extensions/web-access/github-extract.ts",
);

const canary = () => {
  const dir = mkdtempSync(path.join(sandbox, "victim-"));
  writeFileSync(path.join(dir, "keep"), "x");
  return dir;
};

test("encoded traversal in owner never deletes outside the clone root", async () => {
  const victim = canary();
  const url = `https://github.com/..%2F/${path.basename(victim)}`;
  assert.equal(await extractGitHub(url), null);
  assert.ok(existsSync(path.join(victim, "keep")));
});

test("encoded traversal in ref never deletes outside the clone root", async () => {
  const victim = canary();
  const url = `https://github.com/o/r/tree/x%2F..%2F..%2F..%2F${path.basename(victim)}`;
  assert.equal(await extractGitHub(url), null);
  assert.ok(existsSync(path.join(victim, "keep")));
});

test("names GitHub allows still parse", () => {
  assert.deepEqual(parseGitHubUrl("https://github.com/my-org/repo.name_2/tree/v1.2.3/src/a.ts"), {
    owner: "my-org",
    repo: "repo.name_2",
    ref: "v1.2.3",
    refIsFullSha: false,
    path: "src/a.ts",
    type: "tree",
  });
});

test("a README symlinked outside the clone is not read", async () => {
  const secret = path.join(sandbox, "secret.txt");
  writeFileSync(secret, "SECRET_API_KEY=sk-test-123");
  process.env.STUB_GIT_README = secret;
  try {
    const result = await extractGitHub("https://github.com/owner/readme-link");
    assert.ok(result, "clone of a well-formed URL should succeed");
    assert.doesNotMatch(result.content, /sk-test-123/);
  } finally {
    delete process.env.STUB_GIT_README;
  }
});
