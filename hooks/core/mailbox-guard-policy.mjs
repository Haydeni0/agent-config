/** Pure policy for the mailbox turn-end guard: block a Stop while unread mesh
 * mail waits, with the fix commands in the reason.
 *
 * One forced follow-up per stop chain: when the harness reports
 * stopHookActive the stop is allowed regardless of mail, so a session that
 * still ends with unread mail ends gracefully (the next turn's take and the
 * sender's poke protocol take over) and the harness's consecutive-block cap
 * is never approached. */

export function decide({ stopHookActive, memberships }) {
  const withUnread = (memberships ?? []).filter(
    (membership) => Array.isArray(membership.unreadLines) && membership.unreadLines.length > 0,
  );
  if (stopHookActive || withUnread.length === 0) return { block: false, reason: "" };
  const reason = [
    `Unread mesh mail: ${withUnread.reduce((n, m) => n + m.unreadLines.length, 0)} message(s) waiting.`,
    ...withUnread.flatMap((membership) => [
      `${membership.member} (${membership.mailbox}):`,
      ...membership.unreadLines,
    ]),
    ...withUnread.map(
      (membership) =>
        `Run ${membership.mailbox}/bin/mailbox take, act on or defer everything it prints, then run ${membership.mailbox}/bin/mailbox ack.`,
    ),
    "(mailbox turn-end guard)",
  ].join("\n");
  return { block: true, reason };
}
