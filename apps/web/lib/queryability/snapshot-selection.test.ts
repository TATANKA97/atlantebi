import { describe, expect, it } from "vitest";

import {
  snapshotIdForGraphDisplay,
  snapshotIdForGraphRebuild
} from "./snapshot-selection";

describe("queryability snapshot selection", () => {
  it("loads the latest snapshot when the latest graph is selected implicitly", () => {
    expect(
      snapshotIdForGraphDisplay({
        graphExplicitlySelected: false,
        graphSnapshotId: "graph-snapshot",
        requestedSnapshotId: undefined
      })
    ).toBeUndefined();
  });

  it("preserves graph provenance for an explicitly selected graph version", () => {
    expect(
      snapshotIdForGraphDisplay({
        graphExplicitlySelected: true,
        graphSnapshotId: "graph-snapshot",
        requestedSnapshotId: undefined
      })
    ).toBe("graph-snapshot");
  });

  it("uses an explicitly requested snapshot for display and rebuild", () => {
    const displayedSnapshotId = snapshotIdForGraphDisplay({
      graphExplicitlySelected: true,
      graphSnapshotId: "graph-snapshot",
      requestedSnapshotId: "latest-snapshot"
    });

    expect(displayedSnapshotId).toBe("latest-snapshot");
    expect(
      snapshotIdForGraphRebuild({
        displayedSnapshotId,
        graphSnapshotId: "graph-snapshot"
      })
    ).toBe("latest-snapshot");
  });
});
