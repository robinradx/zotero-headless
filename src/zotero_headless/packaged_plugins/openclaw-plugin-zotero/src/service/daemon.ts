// src/service/daemon.ts
import { spawn, type ChildProcess } from "node:child_process";
import type { DaemonConfig, CliConfig } from "../types.js";

export interface DaemonServiceState {
  owned: boolean;
  process: ChildProcess | null;
}

export class DaemonService {
  private daemonConfig: DaemonConfig;
  private cliConfig: CliConfig;
  private state: DaemonServiceState = { owned: false, process: null };
  private logger: { info?: (...args: unknown[]) => void; warn?: (...args: unknown[]) => void };

  constructor(
    daemonConfig: DaemonConfig,
    cliConfig: CliConfig,
    logger: { info?: (...args: unknown[]) => void; warn?: (...args: unknown[]) => void },
  ) {
    this.daemonConfig = daemonConfig;
    this.cliConfig = cliConfig;
    this.logger = logger;
  }

  private async isDaemonReachable(): Promise<boolean> {
    try {
      const res = await fetch(
        `http://${this.daemonConfig.host}:${this.daemonConfig.port}/health`,
      );
      return res.ok;
    } catch {
      return false;
    }
  }

  private async waitForDaemon(timeoutMs: number): Promise<boolean> {
    const start = Date.now();
    while (Date.now() - start < timeoutMs) {
      if (await this.isDaemonReachable()) return true;
      await new Promise((r) => setTimeout(r, 500));
    }
    return false;
  }

  async start(): Promise<void> {
    // Check if already running
    if (await this.isDaemonReachable()) {
      this.state.owned = false;
      this.logger.info?.("Zotero daemon already running, attaching");
      return;
    }

    if (!this.daemonConfig.autoStart) {
      this.logger.info?.("Zotero daemon not running, autoStart disabled — using CLI fallback");
      return;
    }

    // Try to start the daemon
    this.logger.info?.("Starting zotero-headless daemon...");
    try {
      const binary = this.cliConfig.binary.replace(/^zhl$/, "zhl-daemon");
      const daemonBinary = binary.endsWith("-daemon") ? binary : `${binary}-daemon`;

      const proc = spawn(
        daemonBinary,
        [
          "serve",
          "--host", this.daemonConfig.host,
          "--port", String(this.daemonConfig.port),
        ],
        {
          stdio: "ignore",
          detached: true,
        },
      );

      proc.unref();
      this.state.process = proc;

      // Wait for daemon to be ready
      const ready = await this.waitForDaemon(10_000);
      if (ready) {
        this.state.owned = true;
        this.logger.info?.("Zotero daemon started successfully");
      } else {
        this.logger.warn?.(
          "Zotero daemon did not respond within 10s — using CLI fallback",
        );
        this.state.process = null;
      }
    } catch (err) {
      this.logger.warn?.(
        `Failed to start zotero daemon: ${err instanceof Error ? err.message : String(err)} — using CLI fallback`,
      );
    }
  }

  async stop(): Promise<void> {
    if (this.state.owned && this.state.process) {
      this.logger.info?.("Stopping owned zotero daemon...");
      this.state.process.kill("SIGTERM");
      this.state.process = null;
      this.state.owned = false;
    }
  }

  isOwned(): boolean {
    return this.state.owned;
  }
}
