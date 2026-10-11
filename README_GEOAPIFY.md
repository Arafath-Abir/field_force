# Geoapify Travel Log Integration (Odoo 14)

## Configuration

1. Open **Field Force → Configuration → Location API Settings**.
2. Enter only your Geoapify API key in **Geoapify API Key**.
3. Keep **Geoapify Base URL** as `https://api.geoapify.com`.
4. Keep **Country Code** as `bd` and **Result Language** as `en`.
5. Save, then click **Test Geoapify Connections**.

## Travel Log behaviour

- Type at least 3 characters in **From** or **To**.
- Select a returned location suggestion.
- When both locations and journey mode are selected, road distance and estimated duration are calculated automatically.
- Fare is calculated using the existing Fare Configuration slabs.
- If the route API is temporarily unavailable, the module keeps the prior safe fallback and shows a straight-line distance.

## API endpoints used

- Autocomplete: `/v1/geocode/autocomplete`
- Routing: `/v1/routing`

The API key is stored in Odoo system parameters and is not embedded in browser JavaScript.
