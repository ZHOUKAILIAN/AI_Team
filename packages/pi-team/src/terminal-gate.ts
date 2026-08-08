import { createInterface, type Interface } from "node:readline/promises";
import { stdin as input, stdout as output } from "node:process";
import type { GateContext, HumanDecision, HumanGate } from "./types.js";

export type TerminalHumanGateOptions = {
  input?: NodeJS.ReadableStream;
  output?: NodeJS.WritableStream;
};

export class TerminalHumanGate implements HumanGate {
  private readonly input: NodeJS.ReadableStream;
  private readonly output: NodeJS.WritableStream;
  private readline?: Interface;

  constructor(options: TerminalHumanGateOptions = {}) {
    this.input = options.input ?? input;
    this.output = options.output ?? output;
  }

  async confirm(context: GateContext): Promise<HumanDecision> {
    this.write(`\n[需要确认] ${context.stage} / ${context.kind} 阶段已完成（run: ${context.runId}）\n`);
    this.write(`结果：${context.output.output || "（无文本输出）"}\n`);
    this.write("[y] approve  [e] edit/继续  [r] retry  [p] pause  [q] stop\n");
    const readline = this.readline ??= createInterface({ input: this.input, output: this.output });
    while (true) {
      const answer = (await readline.question("> ")).trim().toLowerCase();
      if (answer === "y" || answer === "approve") return "approve";
      if (answer === "e" || answer === "edit") return "edit";
      if (answer === "r" || answer === "retry") return "retry";
      if (answer === "p" || answer === "pause") return "pause";
      if (answer === "q" || answer === "stop") return "stop";
      this.write("请输入 y/e/r/p/q：\n");
    }
  }

  close(): void {
    this.readline?.close();
  }

  private write(message: string): void {
    this.output.write(message);
  }
}
