'use client'

import { useState } from 'react'
import { KeyRound, Save, UserPlus } from 'lucide-react'
import { organisation, people, type S } from '@/lib/api'
import { useAction, useApi } from '@/lib/use-api'
import { Button } from '@/components/ui/primitives'
import { Checkbox, Field, Input, Select } from '@/components/ui/forms'
import { Modal, useToast } from '@/components/ui/feedback'
import { Card, PanelHeader } from '@/components/ui/surfaces'

/** The five roles the SRS names, plus the read-only evaluator account for judges. */
export const ROLE_OPTIONS: Array<[string, string]> = [
  ['customer', 'Customer'],
  ['agent', 'Agent'],
  ['reviewer', 'Reviewer'],
  ['manager', 'Manager'],
  ['admin', 'Administrator'],
  ['evaluator', 'Evaluator (read-only judge)'],
]
const STAFF_TEAM_ROLES = new Set(['agent', 'reviewer', 'manager'])

function useTeams() {
  const org = useApi(() => organisation.get())
  return org.data?.departments ?? []
}

/** An administrator provisions an account; staff roles are never self-assigned. */
export function AddUser({ onCreated }: { onCreated: (row: S['PersonRow']) => void }) {
  const toast = useToast()
  const teams = useTeams()
  const [open, setOpen] = useState(false)
  const blank = { full_name: '', email: '', role: 'agent', department_code: '', password: '' }
  const [form, setForm] = useState(blank)
  const create = useAction(() => people.create({ ...form, department_code: form.department_code || null }))
  const ready = form.full_name.trim().length >= 2 && /\S+@\S+\.\S+/.test(form.email) && form.password.length >= 8
  const set = (k: keyof typeof blank, v: string) => setForm((f) => ({ ...f, [k]: v }))

  return (
    <>
      <Button icon={<UserPlus size={15} aria-hidden />} onClick={() => setOpen(true)}>Add a user</Button>
      <Modal open={open} onClose={() => setOpen(false)} title="Add a user"
        footer={<>
          <Button variant="ghost" onClick={() => setOpen(false)}>Cancel</Button>
          <Button loading={create.pending} disabled={!ready}
            onClick={async () => {
              const row = await create.run()
              if (row) { toast('ok', `${row.full_name} can now sign in as ${row.role}.`); setOpen(false); setForm(blank); onCreated(row) }
              else if (create.error) toast('err', create.error)
            }}>Create account</Button>
        </>}>
        <div className="flex flex-col gap-3">
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label="Full name" required>{(id) => <Input id={id} value={form.full_name} onChange={(e) => set('full_name', e.target.value)} />}</Field>
            <Field label="Email" required>{(id) => <Input id={id} type="email" value={form.email} onChange={(e) => set('email', e.target.value)} />}</Field>
          </div>
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label="Role" required>{(id) => (
              <Select id={id} value={form.role} onChange={(e) => set('role', e.target.value)}>
                {ROLE_OPTIONS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
              </Select>
            )}</Field>
            <Field label="Team" hint={STAFF_TEAM_ROLES.has(form.role) ? 'Agents see their team’s complaints.' : 'Not needed for this role.'}>{(id) => (
              <Select id={id} value={form.department_code} onChange={(e) => set('department_code', e.target.value)}>
                <option value="">No team</option>
                {teams.map((d) => <option key={d.code} value={d.code}>{d.name}</option>)}
              </Select>
            )}</Field>
          </div>
          <Field label="Temporary password" required hint="At least 8 characters. Ask them to change it after signing in.">
            {(id) => <Input id={id} type="text" autoComplete="new-password" value={form.password} onChange={(e) => set('password', e.target.value)} />}
          </Field>
        </div>
      </Modal>
    </>
  )
}

/**
 * Role, team, status and password for one account. Changing a role or
 * disabling the account signs the person out everywhere at once; the server
 * refuses to let an administrator demote or disable themselves.
 */
export function ManageAccount({ person, self, onSaved }: { person: S['PersonRow']; self: boolean; onSaved: () => void }) {
  const toast = useToast()
  const teams = useTeams()
  const teamCode = teams.find((d) => d.name === person.department)?.code ?? ''
  const [role, setRole] = useState(person.role)
  const [team, setTeam] = useState<string | null>(null)
  const [active, setActive] = useState(person.is_active)
  const [password, setPassword] = useState('')
  const currentTeam = team ?? teamCode

  const changes: S['PersonUpdate'] = {}
  if (role !== person.role) changes.role = role
  if (team !== null && team !== teamCode) changes.department_code = team
  if (active !== person.is_active) changes.is_active = active
  if (password) changes.password = password
  const dirty = Object.keys(changes).length > 0
  const save = useAction(() => people.update(person.id, changes))

  return (
    <Card radius="xl">
      <PanelHeader title="Manage account" eyebrow="Administrator" />
      <div className="flex flex-col gap-3">
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="Role" hint={self ? 'You cannot change your own role.' : undefined}>{(id) => (
            <Select id={id} value={role} disabled={self} onChange={(e) => setRole(e.target.value)}>
              {ROLE_OPTIONS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
            </Select>
          )}</Field>
          <Field label="Team">{(id) => (
            <Select id={id} value={currentTeam} onChange={(e) => setTeam(e.target.value)}>
              <option value="">No team</option>
              {teams.map((d) => <option key={d.code} value={d.code}>{d.name}</option>)}
            </Select>
          )}</Field>
        </div>
        <Field label="New password" hint="Leave empty to keep the current one. At least 8 characters.">
          {(id) => <Input id={id} type="text" autoComplete="new-password" value={password} onChange={(e) => setPassword(e.target.value)} placeholder="Set a new password" />}
        </Field>
        <Checkbox label={self ? 'Active (you cannot disable your own account)' : 'Active — can sign in'} checked={active} disabled={self} onChange={(e) => setActive(e.target.checked)} />
        {(changes.role || changes.is_active === false || changes.password) && (
          <p className="text-[12.5px] text-warning">Saving signs {person.full_name} out of every device, so the change applies at once.</p>
        )}
        <Button className="self-start" icon={changes.password ? <KeyRound size={15} aria-hidden /> : <Save size={15} aria-hidden />} disabled={!dirty || (password.length > 0 && password.length < 8)} loading={save.pending}
          onClick={async () => {
            const row = await save.run()
            if (row) { toast('ok', 'Account updated.'); setPassword(''); setTeam(null); onSaved() }
            else if (save.error) toast('err', save.error)
          }}>Save changes</Button>
      </div>
    </Card>
  )
}
