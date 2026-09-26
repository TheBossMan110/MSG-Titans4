'use client'

import { useState } from 'react'
import { Hand, UserRoundCheck, UserRoundX } from 'lucide-react'
import { complaints, people, type S } from '@/lib/api'
import { useAuth } from '@/lib/auth-context'
import { useAction, useApi } from '@/lib/use-api'
import { Button } from '@/components/ui/primitives'
import { Select } from '@/components/ui/forms'
import { useToast } from '@/components/ui/feedback'

const ASSIGNERS = ['manager', 'reviewer', 'admin']

/**
 * Who handles this complaint, and the way to change it (FR ii).
 *
 * Managers, reviewers and administrators assign it to anyone on the staff. An
 * agent takes it for themselves or hands back their own -- they do not hand
 * work to others. Evaluators read. The server enforces the same rules.
 */
export function AssignControl({ complaint, onChanged }: { complaint: S['ComplaintDetail']; onChanged: () => void }) {
  const { user } = useAuth()
  const toast = useToast()
  const assigner = Boolean(user && ASSIGNERS.includes(user.role))
  const staff = useApi(() => people.staff(), [], assigner)
  const [target, setTarget] = useState('')
  const act = useAction((id: string | null) => complaints.assign(complaint.public_ref, id))
  const holder = complaint.assigned_to
  const mine = Boolean(user && holder?.id === user.id)

  const run = async (id: string | null, done: string) => {
    const r = await act.run(id)
    if (r) { toast('ok', done); setTarget(''); onChanged() } else if (act.error) toast('err', act.error)
  }

  return (
    <div className="flex flex-wrap items-center gap-2 text-[13.5px]">
      <span className="inline-flex items-center gap-1.5 rounded-full border border-line-soft bg-white/75 px-3 py-1 text-espresso-2">
        {holder ? <UserRoundCheck size={14} className="text-verified" aria-hidden /> : <UserRoundX size={14} className="text-warning" aria-hidden />}
        {holder ? <>Handled by <b className="font-medium text-espresso">{mine ? 'you' : holder.full_name}</b> <span className="capitalize text-taupe-2">· {holder.role}</span></> : 'Not assigned yet'}
      </span>

      {user?.role === 'agent' && !mine && (
        <Button size="sm" variant="secondary" icon={<Hand size={14} aria-hidden />} loading={act.pending}
          onClick={() => run(user.id, 'This complaint is now yours.')}>Take this complaint</Button>
      )}
      {user?.role === 'agent' && mine && (
        <Button size="sm" variant="ghost" loading={act.pending} onClick={() => run(null, 'Handed back to the team.')}>Hand back</Button>
      )}

      {assigner && (
        <>
          <Select aria-label="Assign to" value={target} onChange={(e) => setTarget(e.target.value)} className="h-9 w-auto min-w-[220px] text-[13.5px]">
            <option value="">{holder ? 'Reassign to…' : 'Assign to…'}</option>
            {(staff.data ?? []).filter((p) => p.id !== holder?.id).map((p) => (
              <option key={p.id} value={p.id}>{p.full_name} · {p.role}{p.team ? ` · ${p.team}` : ''}</option>
            ))}
          </Select>
          <Button size="sm" disabled={!target} loading={act.pending}
            onClick={() => run(target, `Assigned to ${(staff.data ?? []).find((p) => p.id === target)?.full_name ?? 'them'}.`)}>Assign</Button>
          {holder && <Button size="sm" variant="ghost" loading={act.pending} onClick={() => run(null, 'Unassigned.')}>Unassign</Button>}
        </>
      )}
    </div>
  )
}
