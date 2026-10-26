# -*- coding: utf-8 -*-
import requests

from odoo import fields, models, _
from odoo.exceptions import UserError


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    ffm_geoapify_api_key = fields.Char(
        string='Geoapify API Key',
        config_parameter='field_force_management.geoapify_api_key',
    )
    ffm_geoapify_base_url = fields.Char(
        string='Geoapify Base URL',
        default='https://api.geoapify.com',
        config_parameter='field_force_management.geoapify_base_url',
    )
    ffm_geoapify_language = fields.Char(
        string='Result Language',
        default='en',
        config_parameter='field_force_management.geoapify_language',
        help='Two-character language code, for example en.',
    )
    ffm_geoapify_country_code = fields.Char(
        string='Country Code',
        default='bd',
        config_parameter='field_force_management.geoapify_country_code',
        help='ISO two-character country code. Keep bd for Bangladesh.',
    )
    ffm_request_timeout = fields.Integer(
        string='API Timeout (Seconds)',
        default=15,
        config_parameter='field_force_management.geoapify_request_timeout',
    )
    ffm_autocomplete_min_chars = fields.Integer(
        string='Minimum Search Characters',
        default=3,
        config_parameter=(
            'field_force_management.geoapify_autocomplete_min_chars'
        ),
    )
    ffm_autocomplete_limit = fields.Integer(
        string='Maximum Suggestions',
        default=8,
        config_parameter='field_force_management.geoapify_autocomplete_limit',
    )
    ffm_travel_auto_bill = fields.Boolean(
        string='Auto Vendor Bill on Travel Confirm',
        default=False,
        config_parameter='field_force_management.travel_auto_bill',
        help='Automatically create draft Vendor Bill when confirming Travel Log',
    )
    ffm_subtree_visibility = fields.Boolean(
        string='RSM/ASM See Full Subtree',
        default=False,
        config_parameter='field_force_management.subtree_visibility',
        help='If enabled, ASM/RSM see full subordinate subtree (child_of) instead of only direct reports.',
    )

    @staticmethod
    def _error_text(response):
        try:
            payload = response.json()
        except ValueError:
            return ''
        if not isinstance(payload, dict):
            return ''
        message = payload.get('message') or payload.get('error') or ''
        if isinstance(message, dict):
            message = message.get('message') or message.get('error') or ''
        return str(message)[:300]

    def action_test_ffm_location_services(self):
        self.ensure_one()
        self.set_values()

        api_key = (self.ffm_geoapify_api_key or '').strip()
        base_url = (
            self.ffm_geoapify_base_url or 'https://api.geoapify.com'
        ).rstrip('/')
        language = (self.ffm_geoapify_language or 'en').strip().lower()
        country_code = (
            self.ffm_geoapify_country_code or 'bd'
        ).strip().lower()
        timeout = max(1, self.ffm_request_timeout or 15)
        limit = min(20, max(1, self.ffm_autocomplete_limit or 8))
        errors = []

        if not api_key:
            errors.append(_('Geoapify API Key is missing.'))
        else:
            headers = {
                'Accept': 'application/json',
                'User-Agent': 'Odoo14-FieldForceManagement/1.0',
            }

            try:
                response = requests.get(
                    '%s/v1/geocode/autocomplete' % base_url,
                    params={
                        'apiKey': api_key,
                        'text': 'Dhaka',
                        'format': 'json',
                        'filter': 'countrycode:%s' % country_code,
                        'limit': min(3, limit),
                        'lang': language,
                    },
                    timeout=timeout,
                    headers=headers,
                )
                if response.status_code != 200:
                    detail = self._error_text(response)
                    errors.append(_(
                        'Geoapify autocomplete test failed (HTTP %s)%s. '
                        'Check the API key and its IP/referrer restrictions.'
                    ) % (
                        response.status_code,
                        ': %s' % detail if detail else '',
                    ))
                else:
                    payload = response.json()
                    results = payload.get('results') or payload.get('features')
                    if not isinstance(results, list) or not results:
                        errors.append(_(
                            'Geoapify autocomplete returned no location results.'
                        ))
            except requests.RequestException as exc:
                errors.append(_(
                    'Geoapify autocomplete connection failed: %s'
                ) % exc.__class__.__name__)
            except ValueError:
                errors.append(_(
                    'Geoapify autocomplete returned invalid JSON.'
                ))

            try:
                response = requests.get(
                    '%s/v1/routing' % base_url,
                    params={
                        'apiKey': api_key,
                        'waypoints': (
                            '23.7104000,90.4074400|23.7150000,90.4120000'
                        ),
                        'mode': 'drive',
                        'format': 'json',
                        'units': 'metric',
                    },
                    timeout=timeout,
                    headers=headers,
                )
                if response.status_code != 200:
                    detail = self._error_text(response)
                    errors.append(_(
                        'Geoapify routing test failed (HTTP %s)%s. '
                        'Check that Routing API access is enabled.'
                    ) % (
                        response.status_code,
                        ': %s' % detail if detail else '',
                    ))
                else:
                    payload = response.json()
                    routes = payload.get('results') or payload.get('features')
                    if not isinstance(routes, list) or not routes:
                        errors.append(_('Geoapify routing returned no route.'))
                    else:
                        route = routes[0]
                        if 'properties' in route:
                            route = route.get('properties') or {}
                        if not route.get('distance'):
                            errors.append(_(
                                'Geoapify routing response did not contain distance.'
                            ))
            except requests.RequestException as exc:
                errors.append(_(
                    'Geoapify routing connection failed: %s'
                ) % exc.__class__.__name__)
            except ValueError:
                errors.append(_('Geoapify routing returned invalid JSON.'))

        if errors:
            raise UserError('\n'.join(errors))

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Connection Successful'),
                'message': _(
                    'Geoapify autocomplete and road-distance routing are working.'
                ),
                'type': 'success',
                'sticky': False,
            },
        }
