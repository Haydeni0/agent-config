import { decide } from '../../../hooks/core/command-policy.mjs'
export { decide } from '../../../hooks/core/command-policy.mjs'

export const BashGuard = async () => ({
  "tool.execute.before": async (input, output) => {
    if (input?.tool !== "bash") return
    const command = output?.args?.command ?? ""
    if (!command) return
    const r = decide(command)
    if (r.deny) throw new Error(r.reason)
  },
})
