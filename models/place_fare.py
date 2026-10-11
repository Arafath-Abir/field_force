# -*- coding: utf-8 -*-
import hashlib
import logging
import math

import requests

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError
from odoo.osv import expression

_logger = logging.getLogger(__name__)


TRANSPORT_MODES = [
    ('bus', 'Bus'),
    ('rickshaw', 'Rickshaw'),
    ('auto_cng', 'Auto / CNG'),
    ('motorcycle', 'Motorcycle'),
    ('uber_pathao', 'Uber / Pathao'),
    ('on_foot', 'On Foot'),
    ('train', 'Train'),
    ('launch', 'Launch / Ferry'),
    ('others', 'Others'),
]


def _haversine_km(lat1, lng1, lat2, lng2):
    """Straight-line fallback distance in kilometres."""
    radius_km = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lng2 - lng1)
    value = (
        math.sin(dphi / 2.0) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2.0) ** 2
    )
    return round(
        radius_km * 2.0 * math.atan2(math.sqrt(value), math.sqrt(1.0 - value)),
        2,
    )


def _float_value(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return False


def _response_error_message(response):
    """Return a short safe provider error without exposing the API key."""
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


class RoutingProviderBase:
    """Abstract provider interface for geocoding and road routing."""

    def search_places(self, query, config):
        raise NotImplementedError

    def get_route(self, lat1, lng1, lat2, lng2, mode, config):
        raise NotImplementedError


class GeoapifyRoutingProvider(RoutingProviderBase):
    """Geoapify provider implementation with strict 3-second timeout protection."""

    def search_places(self, query, config):
        if not config.get('api_key'):
            return []
        url = '%s/v1/geocode/autocomplete' % config['base_url']
        params = {
            'apiKey': config['api_key'],
            'text': query,
            'format': 'json',
            'filter': 'countrycode:%s' % config['country_code'],
            'limit': config['limit'],
            'lang': config['language'],
        }
        try:
            response = requests.get(
                url,
                params=params,
                timeout=min(3.0, float(config.get('timeout', 3.0))),
                headers={
                    'Accept': 'application/json',
                    'User-Agent': 'Odoo14-FieldForceManagement/1.0',
                },
            )
            if response.status_code != 200:
                return []
            payload = response.json()
        except Exception as exc:
            _logger.warning('Geoapify search failed: %s', exc)
            return []

        results = payload.get('results') if isinstance(payload, dict) else []
        return results if isinstance(results, list) else []

    def get_route(self, lat1, lng1, lat2, lng2, mode, config):
        if not config.get('api_key'):
            return False
        route_mode = 'walk' if mode == 'on_foot' else 'drive'
        waypoints = '%.7f,%.7f|%.7f,%.7f' % (lat1, lng1, lat2, lng2)
        url = '%s/v1/routing' % config['base_url']
        params = {
            'apiKey': config['api_key'],
            'waypoints': waypoints,
            'mode': route_mode,
            'format': 'json',
            'units': 'metric',
        }
        try:
            response = requests.get(
                url,
                params=params,
                timeout=min(3.0, float(config.get('timeout', 3.0))),
                headers={
                    'Accept': 'application/json',
                    'User-Agent': 'Odoo14-FieldForceManagement/1.0',
                },
            )
            if response.status_code != 200:
                return False
            payload = response.json()
        except Exception as exc:
            _logger.warning('Geoapify routing failed: %s', exc)
            return False

        route = False
        if isinstance(payload, dict):
            results = payload.get('results') or []
            if isinstance(results, list) and results:
                route = results[0]
            if not route:
                features = payload.get('features') or []
                if isinstance(features, list) and features:
                    route = features[0].get('properties') or {}

        if not isinstance(route, dict):
            return False

        distance_meters = _float_value(route.get('distance')) or 0.0
        duration_seconds = _float_value(route.get('time')) or 0.0
        if distance_meters <= 0:
            return False

        return {
            'distance_km': round(distance_meters / 1000.0, 2),
            'duration_minutes': round(duration_seconds / 60.0, 2) if duration_seconds > 0 else 0.0,
            'source': 'geoapify',
        }


def get_routing_provider(provider_type='geoapify'):
    return GeoapifyRoutingProvider()


class FfmPlace(models.Model):
    _name = 'ffm.place'
    _description = 'Place / Location'
    _order = 'name'
    _rec_name = 'name'

    name = fields.Char(string='Place Name', required=True, index=True)
    address = fields.Char(string='Full Address', index=True)
    address_bn = fields.Char(string='Address (Bangla)')
    city = fields.Char(string='City', index=True)
    area = fields.Char(string='Area', index=True)
    district = fields.Char(string='District', index=True)
    division = fields.Char(string='Division', index=True)
    post_code = fields.Char(string='Post Code')
    lat = fields.Float(string='Latitude', digits=(12, 7))
    lng = fields.Float(string='Longitude', digits=(12, 7))
    provider = fields.Selection(
        [
            ('manual', 'Manual'),
            ('barikoi', 'Barikoi (Legacy)'),
            ('geoapify', 'Geoapify'),
        ],
        default='manual',
        required=True,
        index=True,
    )
    external_ref = fields.Char(string='Provider Reference', index=True)
    active = fields.Boolean(default=True)

    _sql_constraints = [
        ('name_uniq', 'unique(name)', 'Place name must be unique.'),
        (
            'provider_external_ref_uniq',
            'unique(provider, external_ref)',
            'The same provider location already exists.',
        ),
    ]

    @api.model
    def _get_parameter(self, key, default=False):
        return self.env['ir.config_parameter'].sudo().get_param(key, default)

    @api.model
    def _geoapify_config(self):
        try:
            timeout = float(
                self._get_parameter(
                    'field_force_management.geoapify_request_timeout', '15'
                ) or 15
            )
        except (TypeError, ValueError):
            timeout = 15.0
        try:
            minimum_chars = int(
                self._get_parameter(
                    'field_force_management.geoapify_autocomplete_min_chars', '3'
                ) or 3
            )
        except (TypeError, ValueError):
            minimum_chars = 3
        try:
            limit = int(
                self._get_parameter(
                    'field_force_management.geoapify_autocomplete_limit', '8'
                ) or 8
            )
        except (TypeError, ValueError):
            limit = 8

        language = str(
            self._get_parameter(
                'field_force_management.geoapify_language', 'en'
            ) or 'en'
        ).strip().lower()
        country_code = str(
            self._get_parameter(
                'field_force_management.geoapify_country_code', 'bd'
            ) or 'bd'
        ).strip().lower()

        return {
            'api_key': str(
                self._get_parameter(
                    'field_force_management.geoapify_api_key', ''
                ) or ''
            ).strip(),
            'base_url': str(
                self._get_parameter(
                    'field_force_management.geoapify_base_url',
                    'https://api.geoapify.com',
                ) or 'https://api.geoapify.com'
            ).rstrip('/'),
            'timeout': max(1.0, timeout),
            'minimum_chars': max(1, minimum_chars),
            'limit': min(20, max(1, limit)),
            'language': language[:10] or 'en',
            'country_code': country_code[:2] or 'bd',
        }

    def name_get(self):
        result = []
        for record in self:
            label = record.address or record.name or _('Location')
            result.append((record.id, label))
        return result

    @api.model
    def _search_geoapify(self, query):
        config = self._geoapify_config()
        if not config['api_key']:
            return []

        url = '%s/v1/geocode/autocomplete' % config['base_url']
        params = {
            'apiKey': config['api_key'],
            'text': query,
            'format': 'json',
            'filter': 'countrycode:%s' % config['country_code'],
            'limit': config['limit'],
            'lang': config['language'],
        }
        try:
            response = requests.get(
                url,
                params=params,
                timeout=config['timeout'],
                headers={
                    'Accept': 'application/json',
                    'User-Agent': 'Odoo14-FieldForceManagement/1.0',
                },
            )
            if response.status_code != 200:
                _logger.warning(
                    'Geoapify autocomplete failed for %r with HTTP %s: %s',
                    query,
                    response.status_code,
                    _response_error_message(response),
                )
                return []
            payload = response.json()
        except (requests.RequestException, ValueError) as exc:
            _logger.warning('Geoapify autocomplete failed for %r: %s', query, exc)
            return []

        results = payload.get('results') if isinstance(payload, dict) else []
        if not isinstance(results, list):
            results = []

        # Keep compatibility if GeoJSON is returned despite format=json.
        if not results and isinstance(payload, dict):
            features = payload.get('features') or []
            if isinstance(features, list):
                for feature in features:
                    if not isinstance(feature, dict):
                        continue
                    properties = dict(feature.get('properties') or {})
                    geometry = feature.get('geometry') or {}
                    coordinates = geometry.get('coordinates') or []
                    if len(coordinates) >= 2:
                        properties.setdefault('lon', coordinates[0])
                        properties.setdefault('lat', coordinates[1])
                    results.append(properties)

        return results[:config['limit']]

    @api.model
    def _prepare_geoapify_values(self, place):
        if not isinstance(place, dict):
            return False

        latitude = _float_value(place.get('lat') or place.get('latitude'))
        longitude = _float_value(place.get('lon') or place.get('longitude'))
        if latitude is False or longitude is False:
            return False
        if not (-90.0 <= latitude <= 90.0 and -180.0 <= longitude <= 180.0):
            return False

        formatted = str(
            place.get('formatted')
            or place.get('address_line1')
            or place.get('name')
            or ''
        ).strip()
        primary_name = str(
            place.get('name')
            or place.get('address_line1')
            or formatted
            or _('Location')
        ).strip()
        city = str(
            place.get('city')
            or place.get('town')
            or place.get('village')
            or place.get('municipality')
            or ''
        ).strip()
        area = str(
            place.get('suburb')
            or place.get('district')
            or place.get('quarter')
            or place.get('neighbourhood')
            or ''
        ).strip()
        district = str(
            place.get('county')
            or place.get('district')
            or city
            or ''
        ).strip()
        division = str(place.get('state') or '').strip()

        candidate_name = primary_name
        suffix = city or district or area
        if suffix and suffix.lower() not in candidate_name.lower():
            candidate_name = '%s, %s' % (candidate_name, suffix)

        external_ref = place.get('place_id') or place.get('id')
        if not external_ref:
            datasource = place.get('datasource') or {}
            raw = datasource.get('raw') if isinstance(datasource, dict) else {}
            if isinstance(raw, dict):
                external_ref = raw.get('place_id') or raw.get('osm_id')
        if not external_ref:
            raw_key = '%s|%.7f|%.7f' % (
                formatted or candidate_name,
                latitude,
                longitude,
            )
            external_ref = hashlib.sha1(raw_key.encode('utf-8')).hexdigest()

        return {
            'name': candidate_name[:255],
            'address': (formatted or candidate_name)[:255],
            'city': city[:255],
            'area': area[:255],
            'district': district[:255],
            'division': division[:255],
            'post_code': str(place.get('postcode') or '')[:64],
            'lat': latitude,
            'lng': longitude,
            'provider': 'geoapify',
            'external_ref': str(external_ref)[:255],
            'active': True,
        }

    @api.model
    def _unique_place_name(self, values):
        """Return a unique name while keeping the user-facing address readable."""
        Place = self.sudo().with_context(active_test=False)
        candidate = values['name']
        if not Place.search_count([('name', '=', candidate)]):
            return candidate

        formatted = values.get('address') or candidate
        if formatted != candidate and not Place.search_count([('name', '=', formatted)]):
            return formatted

        suffix = (values.get('external_ref') or '')[-8:]
        if not suffix:
            suffix = hashlib.sha1(
                ('%s|%s|%s' % (
                    candidate,
                    values.get('lat'),
                    values.get('lng'),
                )).encode('utf-8')
            ).hexdigest()[-8:]
        return ('%s [%s]' % (candidate, suffix))[:255]

    @api.model
    def _cache_geoapify_places(self, places):
        Place = self.sudo().with_context(active_test=False)
        records = Place.browse()
        for place in places:
            values = self._prepare_geoapify_values(place)
            if not values:
                continue

            record = Place.search([
                ('provider', '=', 'geoapify'),
                ('external_ref', '=', values['external_ref']),
            ], limit=1)
            if not record:
                record = Place.search([
                    ('lat', '>=', values['lat'] - 0.000001),
                    ('lat', '<=', values['lat'] + 0.000001),
                    ('lng', '>=', values['lng'] - 0.000001),
                    ('lng', '<=', values['lng'] + 0.000001),
                ], limit=1)

            if record:
                if record.provider == 'geoapify':
                    update_values = values
                    update_values['name'] = record.name
                else:
                    # Preserve existing manual/legacy identities and enrich only
                    # fields that are missing.
                    update_values = {}
                    for field_name in (
                        'address', 'city', 'area', 'district', 'division',
                        'post_code', 'lat', 'lng',
                    ):
                        if values.get(field_name) and not record[field_name]:
                            update_values[field_name] = values[field_name]
                if update_values:
                    record.write(update_values)
            else:
                values['name'] = self._unique_place_name(values)
                try:
                    with self.env.cr.savepoint():
                        record = Place.create(values)
                except Exception:
                    record = Place.search([
                        '|',
                        '&',
                        ('provider', '=', 'geoapify'),
                        ('external_ref', '=', values['external_ref']),
                        ('name', '=', values['name']),
                    ], limit=1)
            records |= record
        return records

    @api.model
    def name_search(self, name='', args=None, operator='ilike', limit=40):
        args = list(args or [])
        if name:
            local_domain = expression.AND([
                args,
                [
                    '|', '|', '|', '|',
                    ('name', operator, name),
                    ('address', operator, name),
                    ('area', operator, name),
                    ('district', operator, name),
                    ('division', operator, name),
                ],
            ])
        else:
            local_domain = expression.AND([args, [('active', '=', True)]])

        effective_limit = limit or 40
        return self.search(local_domain, limit=effective_limit).name_get()

    @api.model
    def search_geoapify(self, query):
        records = self._cache_geoapify_places(
            self._search_geoapify(query or '')
        )
        return [
            {
                'id': record.id,
                'display': record.address or record.name,
                'short': record.name,
                'lat': record.lat,
                'lng': record.lng,
            }
            for record in records
        ]

    @api.model
    def search_nominatim(self, query):
        """Backward-compatible RPC name used by older cached JS assets."""
        return self.search_geoapify(query)

    @api.model
    def geocode_and_create(self, place_name):
        """Backward-compatible helper used by older client assets."""
        existing = self.search([('name', '=ilike', place_name)], limit=1)
        if existing:
            return existing
        records = self._cache_geoapify_places(
            self._search_geoapify(place_name or '')
        )
        return records[:1]

    def _geoapify_route(self, other_place, mode=False):
        self.ensure_one()
        other_place.ensure_one()
        config = self._geoapify_config()
        if not config['api_key']:
            return False

        route_mode = 'walk' if mode == 'on_foot' else 'drive'
        waypoints = '%.7f,%.7f|%.7f,%.7f' % (
            self.lat,
            self.lng,
            other_place.lat,
            other_place.lng,
        )
        url = '%s/v1/routing' % config['base_url']
        params = {
            'apiKey': config['api_key'],
            'waypoints': waypoints,
            'mode': route_mode,
            'format': 'json',
            'units': 'metric',
        }

        try:
            response = requests.get(
                url,
                params=params,
                timeout=config['timeout'],
                headers={
                    'Accept': 'application/json',
                    'User-Agent': 'Odoo14-FieldForceManagement/1.0',
                },
            )
            if response.status_code != 200:
                _logger.warning(
                    'Geoapify route failed from %s to %s with HTTP %s: %s',
                    self.display_name,
                    other_place.display_name,
                    response.status_code,
                    _response_error_message(response),
                )
                return False
            payload = response.json()
        except (requests.RequestException, ValueError) as exc:
            _logger.warning(
                'Geoapify route failed from %s to %s: %s',
                self.display_name,
                other_place.display_name,
                exc,
            )
            return False

        route = False
        if isinstance(payload, dict):
            results = payload.get('results') or []
            if isinstance(results, list) and results:
                route = results[0]
            if not route:
                features = payload.get('features') or []
                if isinstance(features, list) and features:
                    route = features[0].get('properties') or {}

        if not isinstance(route, dict):
            _logger.warning(
                'Geoapify returned no route from %s to %s.',
                self.display_name,
                other_place.display_name,
            )
            return False

        distance_meters = _float_value(route.get('distance')) or 0.0
        duration_seconds = _float_value(route.get('time')) or 0.0
        if distance_meters <= 0:
            return False

        return {
            'distance_km': round(distance_meters / 1000.0, 2),
            'duration_minutes': round(duration_seconds / 60.0, 2)
            if duration_seconds > 0
            else 0.0,
            'source': 'geoapify',
            'message': _('Geoapify road route'),
        }

    def compute_route_to(self, other_place, mode=False):
        """Return auto-calculated route data for a Journey Leg.

        Geoapify road distance is preferred. Existing module behaviour is kept
        as a safe fallback by returning Haversine distance if routing is
        temporarily unavailable.
        """
        self.ensure_one()
        other_place.ensure_one()
        if not (self.lat and self.lng and other_place.lat and other_place.lng):
            return {
                'distance_km': 0.0,
                'duration_minutes': 0.0,
                'source': 'none',
                'message': _('No coordinates are available for the selected place.'),
            }

        route = self._geoapify_route(other_place, mode=mode)
        if route:
            return route

        distance = _haversine_km(
            self.lat,
            self.lng,
            other_place.lat,
            other_place.lng,
        )
        fallback_speed = 5.0 if mode == 'on_foot' else 30.0
        return {
            'distance_km': distance,
            'duration_minutes': round((distance / fallback_speed) * 60.0, 2)
            if distance
            else 0.0,
            'source': 'fallback',
            'message': _(
                'Straight-line fallback; Geoapify route was unavailable.'
            ),
        }

    def compute_distance_to(self, other_place):
        """Compatibility method retained for existing integrations."""
        return self.compute_route_to(other_place).get('distance_km')


class FfmFareConfig(models.Model):
    _name = 'ffm.fare.config'
    _description = 'Fare Configuration'
    _order = 'mode, from_km'

    mode = fields.Selection(
        TRANSPORT_MODES,
        string='Mode of Journey',
        required=True,
    )
    from_km = fields.Float(string='From (km)', required=True, digits=(6, 1))
    to_km = fields.Float(string='To (km)', required=True, digits=(6, 1))
    fare_tk = fields.Float(string='Fare (Tk)', required=True, digits=(10, 2))
    note = fields.Char(string='Note')

    @api.constrains('from_km', 'to_km')
    def _check_range(self):
        for record in self:
            if record.from_km >= record.to_km:
                raise ValidationError(_('From (km) must be less than To (km).'))

    @api.model
    def get_fare(self, mode, distance_km):
        slab = self.search([
            ('mode', '=', mode),
            ('from_km', '<=', distance_km),
            ('to_km', '>', distance_km),
        ], limit=1, order='from_km asc')
        return slab.fare_tk if slab else 0.0
