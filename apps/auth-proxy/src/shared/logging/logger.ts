import { env, logLevels, type LogLevel } from "../../config/env.js";

type Severity = Exclude<LogLevel, "silent">;
type Fields = Record<string, unknown>;

class Logger {
  private readonly threshold: number;

  constructor(level: LogLevel) {
    this.threshold = logLevels.indexOf(level);
  }

  private enabled(level: Severity): boolean {
    return logLevels.indexOf(level) <= this.threshold;
  }

  private emit(level: Severity, event: string, fields: Fields): void {
    if (!this.enabled(level)) return;
    const line = JSON.stringify({ ts: new Date().toISOString(), level, event, ...fields });
    if (level === "error") console.error(line);
    else if (level === "warn") console.warn(line);
    else console.info(line);
  }

  error(event: string, fields: Fields = {}): void {
    this.emit("error", event, fields);
  }

  warn(event: string, fields: Fields = {}): void {
    this.emit("warn", event, fields);
  }

  info(event: string, fields: Fields = {}): void {
    this.emit("info", event, fields);
  }

  debug(event: string, fields: Fields = {}): void {
    this.emit("debug", event, fields);
  }

  isDebug(): boolean {
    return this.enabled("debug");
  }
}

export const logger = new Logger(env.logLevel);
