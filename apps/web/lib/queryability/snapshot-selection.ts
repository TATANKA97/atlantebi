export function snapshotIdForGraphDisplay({
  graphExplicitlySelected,
  graphSnapshotId,
  requestedSnapshotId
}: {
  graphExplicitlySelected: boolean;
  graphSnapshotId: string;
  requestedSnapshotId: string | undefined;
}) {
  return (
    requestedSnapshotId ??
    (graphExplicitlySelected ? graphSnapshotId : undefined)
  );
}

export function snapshotIdForGraphRebuild({
  displayedSnapshotId,
  graphSnapshotId
}: {
  displayedSnapshotId: string | undefined;
  graphSnapshotId: string;
}) {
  return displayedSnapshotId ?? graphSnapshotId;
}
