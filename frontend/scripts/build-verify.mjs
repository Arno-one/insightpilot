import { spawn } from "node:child_process";
import { existsSync } from "node:fs";
import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const currentDir = path.dirname(fileURLToPath(import.meta.url));
const projectRoot = path.resolve(currentDir, "..");
const nextBinary = path.join(projectRoot, "node_modules", "next", "dist", "bin", "next");
const verifyDistDir = ".next-verify";
const protectedFiles = ["tsconfig.json", "next-env.d.ts"];

async function backupProtectedFiles() {
  const backups = new Map();

  for (const relativePath of protectedFiles) {
    const absolutePath = path.join(projectRoot, relativePath);

    if (!existsSync(absolutePath)) {
      backups.set(relativePath, null);
      continue;
    }

    backups.set(relativePath, await fs.readFile(absolutePath));
  }

  return backups;
}

async function restoreProtectedFiles(backups) {
  for (const [relativePath, content] of backups.entries()) {
    const absolutePath = path.join(projectRoot, relativePath);

    if (content === null) {
      if (existsSync(absolutePath)) {
        await fs.rm(absolutePath, { force: true });
      }

      continue;
    }

    await fs.writeFile(absolutePath, content);
  }
}

async function cleanupVerifyOutput() {
  const verifyOutputPath = path.join(projectRoot, verifyDistDir);

  if (existsSync(verifyOutputPath)) {
    await fs.rm(verifyOutputPath, { recursive: true, force: true });
  }
}

async function runVerifyBuild() {
  const backups = await backupProtectedFiles();

  await cleanupVerifyOutput();

  const child = spawn(process.execPath, [nextBinary, "build"], {
    cwd: projectRoot,
    env: {
      ...process.env,
      NEXT_DIST_DIR: verifyDistDir,
    },
    stdio: "inherit",
  });

  return new Promise((resolve, reject) => {
    child.on("error", reject);
    child.on("exit", (code) => {
      if (code === 0) {
        resolve();
        return;
      }

      reject(new Error(`Verify build exited with code ${code ?? "unknown"}`));
    });
  }).finally(async () => {
    await restoreProtectedFiles(backups);
    await cleanupVerifyOutput();
  });
}

await runVerifyBuild();
