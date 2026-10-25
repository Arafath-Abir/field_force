# -*- coding: utf-8 -*-
import json
from odoo.tests import tagged
from odoo.tests.common import TransactionCase, HttpCase


def _make_person(env, name, login, group_xmlid, parent=False, password='TeamPass123'):
    user = env['res.users'].with_context(no_reset_password=True).create({
        'name': name,
        'login': login,
        'password': password,
        'groups_id': [(6, 0, [env.ref('base.group_user').id, env.ref(group_xmlid).id])],
    })
    emp = env['hr.employee'].create({
        'name': name,
        'user_id': user.id,
        'parent_id': parent.id if parent else False,
    })
    return user, emp


class TestFFMTerritoryTeam(TransactionCase):

    def setUp(self):
        super().setUp()
        self.Territory = self.env['territory.territory']
        _u, self.rsm = _make_person(self.env, 'Team RSM', 'team_rsm@ffm.test', 'field_force_management.group_ffm_rsm')
        _u, self.asm = _make_person(self.env, 'Team ASM', 'team_asm@ffm.test', 'field_force_management.group_ffm_asm', self.rsm)
        _u, self.fp1 = _make_person(self.env, 'Team FP One', 'team_fp1@ffm.test', 'field_force_management.group_ffm_field_person', self.asm)
        _u, self.fp2 = _make_person(self.env, 'Team FP Two', 'team_fp2@ffm.test', 'field_force_management.group_ffm_field_person', self.asm)

    def test_01_role_from_security_group(self):
        self.assertEqual(self.rsm.ffm_role, 'rsm')
        self.assertEqual(self.asm.ffm_role, 'asm')
        self.assertEqual(self.fp1.ffm_role, 'fp')
        office = self.env['hr.employee'].create({'name': 'Office Staff'})
        self.assertFalse(office.ffm_role, 'Office staff without a field role is not field force')

    def test_02_many_people_per_territory_and_many_territories_per_person(self):
        north = self.Territory.create({'name': 'North', 'member_ids': [(6, 0, [self.rsm.id, self.asm.id, self.fp1.id, self.fp2.id])]})
        south = self.Territory.create({'name': 'South', 'member_ids': [(6, 0, [self.fp1.id])]})
        self.assertEqual(north.rsm_ids, self.rsm)
        self.assertEqual(north.asm_ids, self.asm)
        self.assertEqual(north.fp_ids, self.fp1 | self.fp2)
        self.assertEqual(self.fp1.ffm_territory_ids, north | south)

        north._sync_legacy_links()
        self.assertEqual(north.manager_id, self.asm)
        self.assertIn(north.field_person_id, self.fp1 | self.fp2)

    def test_03_legacy_links_migrate_into_members(self):
        legacy = self.Territory.create({'name': 'Legacy', 'manager_id': self.asm.id, 'field_person_id': self.fp2.id})
        self.assertFalse(legacy.member_ids)
        self.Territory._ffm_migrate_legacy_members()
        self.assertEqual(legacy.member_ids, self.asm | self.fp2)
        # Idempotent
        self.Territory._ffm_migrate_legacy_members()
        self.assertEqual(len(legacy.member_ids), 2)


@tagged('-at_install', 'post_install')
class TestFFMTeamManagementHttp(HttpCase):

    def setUp(self):
        super().setUp()
        self.env['ir.http']._clear_routing_map()
        _make_person(self.env, 'Panel Manager', 'panel_manager@ffm.test',
                     'field_force_management.group_ffm_nsm', password='MgrPass123')
        self.territory = self.env['territory.territory'].create({'name': 'Panel Territory'})
        self.other_territory = self.env['territory.territory'].create({'name': 'Other Territory'})

    def _post(self, url, params):
        resp = self.url_open(url, data=json.dumps({'jsonrpc': '2.0', 'method': 'call', 'params': params}),
                             headers={'Content-Type': 'application/json'})
        return resp.json().get('result', {})

    def test_01_manager_creates_hierarchy_with_logins(self):
        self.authenticate('panel_manager@ffm.test', 'MgrPass123')
        Emp = self.env['hr.employee']

        rsm = self._post('/ff/admin/employee/save', {
            'name': 'Panel RSM', 'role': 'rsm', 'email': 'panel.rsm@ffm.test', 'password': 'RsmPass123',
            'territory_ids': [self.territory.id]})
        self.assertEqual(rsm.get('status'), 'success', rsm)
        asm = self._post('/ff/admin/employee/save', {
            'name': 'Panel ASM', 'role': 'asm', 'email': 'panel.asm@ffm.test', 'password': 'AsmPass123',
            'parent_id': rsm['emp_id'], 'territory_ids': [self.territory.id]})
        self.assertEqual(asm.get('status'), 'success', asm)
        fp = self._post('/ff/admin/employee/save', {
            'name': 'Panel FP', 'role': 'fp', 'email': 'panel.fp@ffm.test', 'password': 'FpPass123',
            'parent_id': asm['emp_id'], 'territory_ids': [self.territory.id, self.other_territory.id]})
        self.assertEqual(fp.get('status'), 'success', fp)

        fp_emp = Emp.browse(fp['emp_id'])
        self.assertEqual(fp_emp.parent_id.id, asm['emp_id'])
        self.assertEqual(Emp.browse(asm['emp_id']).parent_id.id, rsm['emp_id'])
        self.assertEqual(fp_emp.ffm_territory_ids, self.territory | self.other_territory)
        self.assertEqual(fp_emp.user_id.login, 'panel.fp@ffm.test')

        # Validation: duplicate login, bad email, role-incompatible manager
        dup = self._post('/ff/admin/employee/save', {'name': 'Dup', 'role': 'fp', 'email': 'panel.fp@ffm.test', 'password': 'DupPass123'})
        self.assertEqual(dup.get('status'), 'error')
        bad_email = self._post('/ff/admin/employee/save', {'name': 'Bad', 'role': 'fp', 'email': 'not-an-email', 'password': 'BadPass123'})
        self.assertEqual(bad_email.get('status'), 'error')
        bad_parent = self._post('/ff/admin/employee/save', {
            'name': 'Bad Parent', 'role': 'asm', 'email': 'bad.parent@ffm.test', 'password': 'BadPass123',
            'parent_id': asm['emp_id']})
        self.assertEqual(bad_parent.get('status'), 'error')

        # Territory-wise team report lists the territory's people only
        content = self.url_open('/ff/report/cards?report_type=team&mode=daily&territory_id=%d' % self.other_territory.id).content.decode()
        self.assertIn('Panel FP', content)
        self.assertIn('Subordinate Breakdown (1 members)', content)

        # The credentials created from the panel work
        self.authenticate('panel.fp@ffm.test', 'FpPass123')
        self.assertEqual(self.url_open('/ff').status_code, 200)

    def test_02_territory_with_many_members(self):
        self.authenticate('panel_manager@ffm.test', 'MgrPass123')
        _u, fp_a = _make_person(self.env, 'Member A', 'member_a@ffm.test', 'field_force_management.group_ffm_field_person')
        _u, fp_b = _make_person(self.env, 'Member B', 'member_b@ffm.test', 'field_force_management.group_ffm_field_person')
        res = self._post('/ff/admin/territory/save', {'name': 'Shared Territory', 'member_ids': [fp_a.id, fp_b.id]})
        self.assertEqual(res.get('status'), 'success', res)
        terr = self.env['territory.territory'].browse(res['territory_id'])
        self.assertEqual(terr.fp_ids, fp_a | fp_b)
