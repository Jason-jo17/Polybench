import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { Difficulty, ResultStrip, Score, ScoreMeter, Status, scoreTone } from "./ui";

describe("Status", () => {
  it("uses plain labels for each run status", () => {
    const { container } = render(
      <>
        <Status status="PENDING" />
        <Status status="RUNNING" />
        <Status status="COMPLETED" />
        <Status status="FAILED" />
      </>,
    );
    expect(container.textContent).toBe("QueuedRunningCompletedFailed");
    expect(container.querySelector(".status-running")).not.toBeNull();
  });
});

describe("scores", () => {
  it("colours scores by band", () => {
    expect(scoreTone(0.8)).toBe("score-hi");
    expect(scoreTone(0.4)).toBe("score-mid");
    expect(scoreTone(0.39)).toBe("score-lo");
  });

  it("formats the score and fills the meter", () => {
    render(<Score value={0.643} />);
    expect(screen.getByText("64.3%").className).toContain("score-mid");

    const { container } = render(<ScoreMeter value={0.25} />);
    const fill = container.querySelector(".meter > span") as HTMLElement;
    expect(fill.style.width).toBe("25%");
  });

  it("shows a dash for a meter that has no score yet", () => {
    const { container } = render(<ScoreMeter value={0} pending />);
    expect(container.textContent).toBe("—");
  });
});

describe("ResultStrip", () => {
  const cells = (container: HTMLElement) =>
    [...container.querySelectorAll(".cell")].map((c) => c.className.replace("cell", "").trim() || "grey");

  it("draws one cell per task: pass, partial, fail, or grey when nothing has finished", () => {
    const { container } = render(
      <ResultStrip
        total={5}
        scores={[
          { task_id: "a", pass_at_k: 1, samples_done: 2 },
          { task_id: "b", pass_at_k: 0.5, samples_done: 2 },
          { task_id: "c", pass_at_k: 0, samples_done: 2 },
          { task_id: "d", pass_at_k: 0, samples_done: 0 },
        ]}
      />,
    );
    // The fifth task hasn't been reported yet, so it's padded out in grey.
    expect(cells(container)).toEqual(["p", "h", "f", "grey", "grey"]);
  });
});

describe("Difficulty", () => {
  it("labels the level and marks it for the bar styling", () => {
    const { container } = render(<Difficulty level="medium" />);
    expect(container.textContent).toBe("Medium");
    expect(container.querySelector(".diff-medium")).not.toBeNull();
  });
});
