'use client'

import { useState } from 'react'
import { Building2, KeyRound, Save, UserPlus } from 'lucide-react'
import { organisation, people, type S } from '@/lib/api'
import { useAction, useApi } from '@/lib/use-api'
import { Button } from '@/components/ui/primitives'
import { Checkbox, Field, Input, PasswordInput, Select } from '@/components/ui/forms'
import { Modal, useToast } from '@/components/ui/feedback'
import { Card, PanelHeader } from '@/components/ui/surfaces'
import { useAuth } from '@/lib/auth-context'

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

/**
 * An administrator provisions any account; a manager provisions agents for their department.
 */
export function AddUser({
  onCreated,
  fixedRole,
  fixedDepartment,
  triggerLabel,
  title,
}: {
  onCreated: (row: S['PersonRow']) => void
  fixedRole?: string
  fixedDepartment?: string
  triggerLabel?: string
  title?: string
}) {
  const toast = useToast()
  const { user } = useAuth()
  const isManager = user?.role === 'manager'
  const teams = useTeams()

  const defaultRole = fixedRole || (isManager ? 'agent' : 'agent')
  const managerDeptCode = user?.department?.code ?? ''
  const defaultDept = fixedDepartment || (isManager ? managerDeptCode : '')

  const [open, setOpen] = useState(false)
  const blank = { full_name: '', email: '', role: defaultRole, department_code: defaultDept, password: '' }
  const [form, setForm] = useState(blank)

  const handleOpen = () => {
    setForm({
      full_name: '',
      email: '',
      role: fixedRole || (isManager ? 'agent' : 'agent'),
      department_code: fixedDepartment || (isManager ? (user?.department?.code ?? '') : ''),
      password: '',
    })
    setOpen(true)
  }

  const create = useAction(() => people.create({ ...form, department_code: form.department_code || null }))
  const ready = form.full_name.trim().length >= 2 && /\S+@\S+\.\S+/.test(form.email) && form.password.length >= 8
  const set = (k: keyof typeof blank, v: string) => setForm((f) => ({ ...f, [k]: v }))

  const lockRole = Boolean(fixedRole) || isManager
  const lockDept = Boolean(fixedDepartment) || isManager

  return (
    <>
      <Button icon={<UserPlus size={15} aria-hidden />} onClick={handleOpen}>
        {triggerLabel ?? (isManager ? 'Add agent' : 'Add a user')}
      </Button>
      <Modal
        open={open}
        onClose={() => setOpen(false)}
        title={title ?? (isManager ? 'Add department agent' : 'Add a user')}
        footer={
          <>
            <Button variant="ghost" onClick={() => setOpen(false)}>
              Cancel
            </Button>
            <Button
              loading={create.pending}
              disabled={!ready}
              onClick={async () => {
                const row = await create.run()
                if (row) {
                  toast('ok', `${row.full_name} can now sign in as ${row.role}.`)
                  setOpen(false)
                  setForm(blank)
                  onCreated(row)
                } else if (create.error) {
                  toast('err', create.error)
                }
              }}
            >
              Create account
            </Button>
          </>
        }
      >
        <div className="flex flex-col gap-3">
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label="Full name" required>
              {(id) => <Input id={id} value={form.full_name} onChange={(e) => set('full_name', e.target.value)} />}
            </Field>
            <Field label="Email" required>
              {(id) => <Input id={id} type="email" value={form.email} onChange={(e) => set('email', e.target.value)} />}
            </Field>
          </div>
          <div className="grid gap-3 sm:grid-cols-2">
            <Field
              label="Role"
              required
              hint={lockRole ? 'Role is locked to Agent.' : undefined}
            >
              {(id) => (
                <Select
                  id={id}
                  value={form.role}
                  disabled={lockRole}
                  onChange={(e) => set('role', e.target.value)}
                >
                  {ROLE_OPTIONS.map(([v, l]) => (
                    <option key={v} value={v}>
                      {l}
                    </option>
                  ))}
                </Select>
              )}
            </Field>
            <Field
              label="Team"
              hint={
                lockDept
                  ? 'Locked to your department team.'
                  : STAFF_TEAM_ROLES.has(form.role)
                  ? 'Agents see their team’s complaints.'
                  : 'Not needed for this role.'
              }
            >
              {(id) => (
                <Select
                  id={id}
                  value={form.department_code}
                  disabled={lockDept}
                  onChange={(e) => set('department_code', e.target.value)}
                >
                  <option value="">No team</option>
                  {teams.map((d) => (
                    <option key={d.code} value={d.code}>
                      {d.name}
                    </option>
                  ))}
                </Select>
              )}
            </Field>
          </div>
          <Field
            label="Temporary password"
            required
            hint="At least 8 characters. Ask them to change it after signing in."
          >
            {(id) => (
              <PasswordInput
                id={id}
                autoComplete="new-password"
                value={form.password}
                onChange={(e) => set('password', e.target.value)}
              />
            )}
          </Field>
        </div>
      </Modal>
    </>
  )
}

/**
 * Administrator provisions a new department and optionally creates a manager account for it.
 */
export function AddDepartment({ onCreated }: { onCreated?: (dept: S['TeamOut']) => void }) {
  const toast = useToast()
  const [open, setOpen] = useState(false)
  const [withManager, setWithManager] = useState(true)
  const blank = {
    code: '',
    name: '',
    description: '',
    email: '',
    manager_name: '',
    manager_email: '',
    manager_password: '',
  }
  const [form, setForm] = useState(blank)
  const set = (k: keyof typeof blank, v: string) => setForm((f) => ({ ...f, [k]: v }))

  const create = useAction(() =>
    organisation.createDepartment({
      code: form.code.trim().toUpperCase(),
      name: form.name.trim(),
      description: form.description.trim() || null,
      email: form.email.trim() || null,
      manager_name: withManager && form.manager_name.trim() ? form.manager_name.trim() : null,
      manager_email: withManager && form.manager_email.trim() ? form.manager_email.trim() : null,
      manager_password: withManager && form.manager_password.trim() ? form.manager_password.trim() : null,
    }),
  )

  const ready =
    form.code.trim().length >= 2 &&
    form.name.trim().length >= 2 &&
    (!withManager ||
      (/\S+@\S+\.\S+/.test(form.manager_email) && (form.manager_password.length === 0 || form.manager_password.length >= 8)))

  return (
    <>
      <Button icon={<Building2 size={15} aria-hidden />} onClick={() => setOpen(true)}>
        Add department
      </Button>
      <Modal
        open={open}
        onClose={() => setOpen(false)}
        title="Add a department"
        footer={
          <>
            <Button variant="ghost" onClick={() => setOpen(false)}>
              Cancel
            </Button>
            <Button
              loading={create.pending}
              disabled={!ready}
              onClick={async () => {
                const dept = await create.run()
                if (dept) {
                  toast('ok', `Department ${dept.name} (${dept.code}) created successfully.`)
                  setOpen(false)
                  setForm(blank)
                  onCreated?.(dept)
                } else if (create.error) {
                  toast('err', create.error)
                }
              }}
            >
              Create department
            </Button>
          </>
        }
      >
        <div className="flex flex-col gap-4">
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label="Department code" required hint="Short uppercase identifier (e.g. BILLING, TECH, HR)">
              {(id) => (
                <Input
                  id={id}
                  value={form.code}
                  onChange={(e) => set('code', e.target.value.toUpperCase())}
                  placeholder="e.g. BILLING"
                  className="font-mono uppercase"
                />
              )}
            </Field>
            <Field label="Department name" required hint="Display name of the team">
              {(id) => (
                <Input
                  id={id}
                  value={form.name}
                  onChange={(e) => set('name', e.target.value)}
                  placeholder="e.g. Billing & Accounts"
                />
              )}
            </Field>
          </div>

          <Field label="Description" hint="Optional description of the department's responsibilities">
            {(id) => (
              <Input
                id={id}
                value={form.description}
                onChange={(e) => set('description', e.target.value)}
                placeholder="e.g. Handles payments, invoices, refunds and billing queries"
              />
            )}
          </Field>

          <Field label="Department email" hint="Inbound support mailbox address (optional)">
            {(id) => (
              <Input
                id={id}
                type="email"
                value={form.email}
                onChange={(e) => set('email', e.target.value)}
                placeholder="e.g. billing@supportnova.com"
              />
            )}
          </Field>

          <div className="rounded-xl border border-line-soft bg-sand/30 p-3.5">
            <Checkbox
              label={<span className="font-medium text-espresso">Provision a Department Manager account</span>}
              checked={withManager}
              onChange={(e) => setWithManager(e.target.checked)}
            />
            {withManager && (
              <div className="mt-3 flex flex-col gap-3 border-t border-line-soft pt-3">
                <div className="grid gap-3 sm:grid-cols-2">
                  <Field label="Manager name" hint="Leave empty to use '<Department> Manager'">
                    {(id) => (
                      <Input
                        id={id}
                        value={form.manager_name}
                        onChange={(e) => set('manager_name', e.target.value)}
                        placeholder="e.g. Sarah Jenkins"
                      />
                    )}
                  </Field>
                  <Field label="Manager email" required hint="Manager's corporate email for signing in">
                    {(id) => (
                      <Input
                        id={id}
                        type="email"
                        value={form.manager_email}
                        onChange={(e) => set('manager_email', e.target.value)}
                        placeholder="e.g. sarah.j@supportnova.com"
                      />
                    )}
                  </Field>
                </div>
                <Field
                  label="Temporary password"
                  hint="At least 8 characters. Defaults to SupportNova#2026 if empty."
                >
                  {(id) => (
                    <PasswordInput
                      id={id}
                      autoComplete="new-password"
                      value={form.manager_password}
                      onChange={(e) => set('manager_password', e.target.value)}
                      placeholder="SupportNova#2026"
                    />
                  )}
                </Field>
              </div>
            )}
          </div>
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
