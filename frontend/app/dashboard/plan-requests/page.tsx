'use client'

import { AppShell } from '@/components/layout/app-shell'
import { billing, type S } from '@/lib/api'
import { useAction, useApi, fmtRelative } from '@/lib/use-api'
import { Badge } from '@/components/ui/primitives'
import { Select } from '@/components/ui/forms'
import { Table, Td, Th, Tr } from '@/components/ui/data'
import { Empty, ErrorState, SkeletonRows, useToast } from '@/components/ui/feedback'

export default function PlanRequestsPage() {
  return (
    <AppShell eyebrow="Platform / Plan requests" roles={['superadmin']} wide>
      <PlanRequests />
    </AppShell>
  )
}

type Status = S['PlanRequestStatusIn']['status']
const STATUSES: Array<[Status, string]> = [['NEW', 'New'], ['CONTACTED', 'Contacted'], ['WON', 'Won'], ['LOST', 'Lost']]

/** Companies asking for a plan from the pricing page. Create the company on Companies once it is agreed. */
function PlanRequests() {
  const toast = useToast()
  const q = useApi(() => billing.requests(), [])
  const change = useAction((id: string, status: Status) => billing.setRequestStatus(id, status))

  if (q.error) return <ErrorState title="The requests could not be loaded" message={q.error} onRetry={q.refresh} />
  const data = q.data

  const update = async (id: string, status: Status) => {
    const row = await change.run(id, status)
    if (row) { toast('ok', `${row.company_name} marked ${status.toLowerCase()}.`); q.refresh() }
    else if (change.error) toast('err', change.error)
  }

  return (
    <div className="flex min-w-0 flex-col gap-6">
      <div>
        <p className="eyebrow mb-1">Platform</p>
        <h1 className="display text-h2">Plan requests</h1>
        <p className="mt-2 max-w-[66ch] text-[14.5px] text-taupe-2">
          Companies that asked for a plan on the pricing page. When one is agreed, create it on Companies, or change its plan there.
        </p>
      </div>
      {!data ? <SkeletonRows rows={6} /> : !data.items.length ? <Empty title="No requests yet" body="Requests from the pricing page appear here." /> : (
        <Table>
          <thead>
            <tr>
              <Th>Company</Th><Th>Contact</Th><Th>Plan</Th><Th align="right">Staff</Th><Th align="right">Complaints / month</Th><Th>Received</Th><Th>Status</Th>
            </tr>
          </thead>
          <tbody>
            {data.items.map((r) => (
              <Tr key={r.id}>
                <Td className="max-w-[260px]">
                  <span className="flex items-center gap-2 font-medium text-espresso">
                    <span className="truncate">{r.company_name}</span>
                    {r.existing_customer && <Badge tone="info">Existing</Badge>}
                  </span>
                  {r.message && <span className="block truncate text-[12.5px] text-taupe-2" title={r.message}>{r.message}</span>}
                </Td>
                <Td className="text-[13px]">
                  <span className="block text-espresso">{r.contact_name}</span>
                  <a href={`mailto:${r.email}`} className="block text-espresso-2 underline underline-offset-2">{r.email}</a>
                  {r.phone && <span className="block text-taupe-2">{r.phone}</span>}
                </Td>
                <Td className="whitespace-nowrap text-[13px] capitalize">{r.plan_code} · {r.billing_cycle}</Td>
                <Td align="right" mono>{r.team_size ?? '—'}</Td>
                <Td align="right" mono>{r.monthly_complaints?.toLocaleString() ?? '—'}</Td>
                <Td className="whitespace-nowrap text-[13px] text-taupe-2">{fmtRelative(r.created_at)}</Td>
                <Td>
                  <Select aria-label={`Status of ${r.company_name}`} value={r.status} disabled={change.pending} onChange={(e) => void update(r.id, e.target.value as Status)} className="w-auto">
                    {STATUSES.map(([v, label]) => <option key={v} value={v}>{label}</option>)}
                  </Select>
                </Td>
              </Tr>
            ))}
          </tbody>
        </Table>
      )}
    </div>
  )
}
