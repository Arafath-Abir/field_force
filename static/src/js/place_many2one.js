odoo.define('field_force_management.place_many2one', function (require) {
    'use strict';

    var FieldMany2One = require('web.relational_fields').FieldMany2One;
    var fieldRegistry = require('web.field_registry');

    /**
     * Compatibility alias.
     *
     * Geoapify autocomplete is now handled server-side by ffm.place.name_search,
     * so it works with Odoo's native Many2one dropdown, including editable
     * One2many rows. Keeping this widget name avoids breaking cached/older views.
     */
    fieldRegistry.add('ffm_place', FieldMany2One);

    return FieldMany2One;
});
