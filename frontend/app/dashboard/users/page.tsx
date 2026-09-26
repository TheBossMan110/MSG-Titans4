'use client'

import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import { ShieldCheck } from 'lucide-react'
import { AppShell } from '@/components/layout/app-shell'
import { people } from '@/lib/api'
import { useApi, fmtRelative } from '@/lib/use-api'
import { Badge } from '@/components/ui/primitives'
import { SearchBox } from '@/components/ui/forms'
import { Pagination, Table, Td, Th, Tr } from '@/components/ui/data'
import { Empty, ErrorState, SkeletonRows } from '@/components/ui/feedback'
import { Stat } from '@/components/ui/data'
import { Card } from '@/components/ui/surfaces'
import { useAuth } from '@/lib/auth-context'
import { AddUser } from '@/components/app/user-admin'

const OVERSIGHT = ['manager', 'admin', 'evaluator'] as const
const ROLES: Array<[string, string]> = [['', 'Everyone'], ['customer', 'Customers'], ['agent', 'Agents'], ['reviewer', 'Reviewers'], ['manager', 'Managers'], ['admin', 'Admins'], ['evaluator', 'Evaluators']]
const SIZE = 25

export default function UsersPage() {
  return (
    <AppShell eyebrow="Users" roles={[...OVERSIGHT]} wide>
      <Users />
    </AppShell>
  )
}

function Users() {
  const router = useRouter()
  const { user } = useAuth()
  const isAdmin = user?.role === 'admin'
  const [role, setRole] = useState('')
  const [search, setSearch] = useState('')
  const [typed, setTyped] = useState('')
  const [page, setPage] = useState(1)

  // Typing settles for a moment before the list is asked again.
  useEffect(() => {
    const t = setTimeout(() => { setSearch(typed.trim()); setPage(1) }, 300)
    return () => clearTimeout(t)
  }, [typed])

  const summary = useApi(() => people.summary(), [], true, { live: true })
  const q = useApi(() => people.list({ role: role || undefined, search: search || undefined, page, page_size: SIZE }), [role, search, page], true, { live: true })
  const s = summary.data

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="eyebrow mb-1">{isAdmin ? 'Accounts and permissions' : 'Everyone with an account'}</p>
          <h1 className="display text-h2">{isAdmin ? 'Users & roles' : 'Team'}</h1>
          <p className="mt-2 max-w-[62ch] text-[14.5px] text-taupe-2">
            {isAdmin
              ? 'Every customer and staff account. Add people, give them a role and a team, or disable an account; open one to see their complaints, history and sign-ins.'
              : user?.role === 'manager'
              ? 'Manage support agents in your department and oversee team activity.'
              : 'Every customer and staff account, read only. Open one to see their complaints with their full history, sign-ins and emails. Only an administrator changes roles.'}
          </p>
        </div>
        {(isAdmin || user?.role === 'manager') && (
          <AddUser
            fixedRole={user?.role === 'manager' ? 'agent' : undefined}
            triggerLabel={user?.role === 'manager' ? 'Add department agent' : 'Add a user'}
            onCreated={(row) => { q.refresh(); summary.refresh(); router.push(`/dashboard/users/${row.id}`) }}
          />
        )}
      </div>

      <Card tone="glass" radius="xl" className="grid grid-cols-2 gap-x-6 gap-y-5 sm:grid-cols-4">
        <Stat label="Accounts" value={s?.total} />
        <Stat label="Customers" value={s ? s.by_role.customer ?? 0 : undefined} />
        <Stat label="New this week" value={s?.new_7d} tone={s?.new_7d ? 'verified' : 'neutral'} />
        <Stat label="Signed in today" value={s?.signed_in_today} />
      </Card>

      <div className="flex flex-wrap items-center gap-3">
        <div className="flex flex-wrap gap-1.5" role="group" aria-label="Role">
          {ROLES.map(([value, label]) => (
            <button key={label} type="button" onClick={() => { setRole(value); setPage(1) }} aria-pressed={role === value}
              className={role === value ? 'rounded-full bg-espresso px-3 py-1.5 text-[13px] text-ink-on-dark' : 'rounded-full border border-line bg-white/70 px-3 py-1.5 text-[13px] text-espresso-2 hover:bg-white'}>
              {label}{value && s?.by_role[value] != null ? ` · ${s.by_role[value]}` : ''}
            </button>
          ))}
        </div>
        <SearchBox value={typed} onChange={setTyped} placeholder="Search name, email or customer reference" className="ml-auto w-full sm:w-[340px]" />
      </div>

      {q.error ? <ErrorState message={q.error} onRetry={q.refresh} /> : !q.data ? <SkeletonRows rows={8} /> : !q.data.items.length ? (
        <Empty title="No one matches" body={search ? `Nobody matches “${search}”.` : 'No accounts with this role yet.'} />
      ) : (
        <>
          <Table>
            <thead>
              <tr><Th>Person</Th><Th>Role</Th><Th>Joined</Th><Th>Last sign-in</Th><Th align="right">Complaints</Th><Th>Security</Th></tr>
            </thead>
            <tbody>
              {q.data.items.map((u) => (
                <Tr key={u.id} onClick={() => router.push(`/dashboard/users/${u.id}`)}>
                  <Td>
                    <span className="flex items-center gap-3">
                      <span className="inline-flex size-8 shrink-0 items-center justify-center rounded-full bg-espresso text-[11.5px] font-semibold text-ink-on-dark" aria-hidden>
                        {u.full_name.split(/\s+/).map((w) => w[0]).slice(0, 2).join('').toUpperCase()}
                      </span>
                      <span className="min-w-0">
                        <span className="block truncate font-medium text-espresso">{u.full_name}</span>
                        <span className="block truncate text-[12.5px] text-taupe-2">{u.email}{u.customer_ref ? ` · ${u.customer_ref}` : ''}</span>
                      </span>
                    </span>
                  </Td>
                  <Td>
                    <Badge tone={u.role === 'customer' ? 'neutral' : 'ai'}><span className="capitalize">{u.role}</span></Badge>
                    {u.department ? <span className="mt-1 block text-[12px] text-taupe-2">{u.department}</span> : null}
                    {!u.is_active ? <Badge tone="critical" className="ml-1">Disabled</Badge> : null}
                  </Td>
                  <Td><span className="whitespace-nowrap text-[13.5px]">{fmtRelative(u.created_at)}</span></Td>
                  <Td><span className="whitespace-nowrap text-[13.5px]">{u.last_login_at ? fmtRelative(u.last_login_at) : <span className="text-taupe">Never</span>}</span></Td>
                  <Td align="right">
                    {u.role === 'customer' ? (
                      <span className="tnum">{u.complaints}{u.open_complaints ? <span className="text-taupe-2"> · {u.open_complaints} open</span> : null}</span>
                    ) : (
                      <span className="tnum text-taupe-2">{u.assigned ? `${u.assigned} assigned` : '—'}</span>
                    )}
                  </Td>
                  <Td>{u.mfa_on ? <Badge tone="verified"><ShieldCheck size={12} aria-hidden /> Two-step on</Badge> : <span className="text-[12.5px] text-taupe">Password only</span>}</Td>
                </Tr>
              ))}
            </tbody>
          </Table>
          <Pagination page={page} size={SIZE} total={q.data.total} onPage={setPage} />
        </>
      )}
    </div>
  )
}
