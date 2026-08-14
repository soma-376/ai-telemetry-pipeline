export class AppError extends Error {
  constructor(
    public readonly statusCode: number,
    message: string,
    public readonly code: string,
    public readonly outcome?: "rejected" | "failed",
  ) {
    super(message);
    this.name = "AppError";
  }
}
