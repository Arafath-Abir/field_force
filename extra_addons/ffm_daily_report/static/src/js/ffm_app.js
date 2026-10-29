/**
 * FFM Marketer Mobile Application Runtime
 * Lightweight vanilla JavaScript helper library
 */
(function(window) {
    'use strict';

    var FFM = window.FFM || {};

    // 1. Client UUID Generator (Idempotency token)
    FFM.getOrGenerateUUID = function(key) {
        key = key || 'ffm_active_client_uuid';
        var stored = sessionStorage.getItem(key);
        if (stored) {
            return stored;
        }
        var newUuid = '';
        if (window.crypto && window.crypto.randomUUID) {
            newUuid = window.crypto.randomUUID();
        } else {
            // RFC4122 v4 Fallback
            newUuid = 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function(c) {
                var r = Math.random() * 16 | 0, v = c === 'x' ? r : (r & 0x3 | 0x8);
                return v.toString(16);
            });
        }
        sessionStorage.setItem(key, newUuid);
        return newUuid;
    };

    FFM.resetUUID = function(key) {
        key = key || 'ffm_active_client_uuid';
        sessionStorage.removeItem(key);
    };

    // 2. Double Tap / Multi-Submit Guard
    FFM.doubleTapGuard = function(buttonElement, loadingText) {
        if (!buttonElement) return function() {};
        
        var originalText = buttonElement.innerHTML;
        buttonElement.disabled = true;
        buttonElement.innerHTML = loadingText || 'Please wait...';

        return function releaseGuard() {
            buttonElement.disabled = false;
            buttonElement.innerHTML = originalText;
        };
    };

    // 3. LocalStorage Form Drafts
    FFM.saveDraft = function(formId, dataObj) {
        try {
            localStorage.setItem('ffm_draft_' + formId, JSON.stringify(dataObj));
        } catch (e) {
            console.warn('Could not save draft to localStorage', e);
        }
    };

    FFM.loadDraft = function(formId) {
        try {
            var raw = localStorage.getItem('ffm_draft_' + formId);
            return raw ? JSON.parse(raw) : null;
        } catch (e) {
            console.warn('Could not read draft from localStorage', e);
            return null;
        }
    };

    FFM.clearDraft = function(formId) {
        try {
            localStorage.removeItem('ffm_draft_' + formId);
        } catch (e) {
            console.warn('Could not clear draft', e);
        }
    };

    // 4. Toast Notifications
    FFM.showToast = function(message, type) {
        var container = document.getElementById('ffm-toast-container');
        if (!container) {
            container = document.createElement('div');
            container.id = 'ffm-toast-container';
            container.className = 'ffm-toast-container';
            document.body.appendChild(container);
        }

        var toast = document.createElement('div');
        toast.className = 'ffm-toast ' + (type === 'error' ? 'ffm-toast-danger' : 'ffm-toast-success');
        toast.innerText = message;
        container.appendChild(toast);

        setTimeout(function() {
            if (toast && toast.parentNode) {
                toast.parentNode.removeChild(toast);
            }
        }, 4000);
    };

    // After a form is saved, go back to the home page and show the message there
    FFM.goHome = function(message) {
        try { sessionStorage.setItem('ffm_flash', message || ''); } catch (e) {}
        window.location.href = '/ff';
    };

    FFM.showFlash = function() {
        var message = null;
        try {
            message = sessionStorage.getItem('ffm_flash');
            sessionStorage.removeItem('ffm_flash');
        } catch (e) {}
        if (message) FFM.showToast(message, 'success');
    };

    // 5. Geolocation Capture Helper
    FFM.captureGPS = function(onSuccess, onError) {
        if (!navigator.geolocation) {
            onError(new Error('Geolocation is not supported by this browser.'));
            return;
        }

        var options = {
            enableHighAccuracy: true,
            timeout: 15000,
            maximumAge: 0
        };

        navigator.geolocation.getCurrentPosition(
            function(position) {
                onSuccess({
                    latitude: position.coords.latitude,
                    longitude: position.coords.longitude,
                    accuracy: position.coords.accuracy,
                    timestamp: position.timestamp
                });
            },
            function(err) {
                var msg = 'Unable to retrieve location.';
                if (err.code === 1) {
                    msg = 'GPS permission denied. Please enable location access in browser settings.';
                } else if (err.code === 2) {
                    msg = 'Position unavailable. GPS or network signal not found.';
                } else if (err.code === 3) {
                    msg = 'GPS connection timed out. Please try again.';
                }
                onError(new Error(msg));
            },
            options
        );
    };

    // 5b. Live Location Gate: every field form is submitted with a fresh GPS fix, never without one
    FFM.withLiveLocation = function(buttonElement, loadingText, onLocated) {
        var release = FFM.doubleTapGuard(buttonElement, 'Getting live location...');
        FFM.captureGPS(
            function(pos) {
                if (buttonElement) {
                    buttonElement.innerHTML = loadingText || 'Saving...';
                }
                onLocated({
                    latitude: pos.latitude,
                    longitude: pos.longitude,
                    gps_accuracy: pos.accuracy
                }, release);
            },
            function(err) {
                release();
                FFM.showToast(err.message + ' Not submitted.', 'error');
            }
        );
    };

    // 6. Browser Image Compression Helper (~1280px max, JPEG ~0.7)
    FFM.compressImage = function(file, callback, maxDimension, quality) {
        if (!file) {
            callback(null);
            return;
        }
        maxDimension = maxDimension || 1280;
        quality = (quality !== undefined) ? quality : 0.7;

        var reader = new FileReader();
        reader.onload = function(e) {
            var img = new Image();
            img.onload = function() {
                var width = img.width;
                var height = img.height;

                if (width > maxDimension || height > maxDimension) {
                    if (width > height) {
                        height = Math.round((height * maxDimension) / width);
                        width = maxDimension;
                    } else {
                        width = Math.round((width * maxDimension) / height);
                        height = maxDimension;
                    }
                }

                var canvas = document.createElement('canvas');
                canvas.width = width;
                canvas.height = height;
                var ctx = canvas.getContext('2d');
                ctx.drawImage(img, 0, 0, width, height);

                var dataUrl = canvas.toDataURL('image/jpeg', quality);
                callback(dataUrl);
            };
            img.onerror = function() {
                callback(null, new Error('Unable to load image.'));
            };
            img.src = e.target.result;
        };
        reader.onerror = function() {
            callback(null, new Error('Unable to read file.'));
        };
        reader.readAsDataURL(file);
    };

    // 6. Manager Panel Actions (Approve, Reject, Check)
    FFM.toggleApproval = function(input) {
        var enabled = input.checked;
        var msg = enabled ? 'Turn ON the approval system?' : 'Turn OFF the approval system? Pending, approved and rejected statuses will be hidden.';
        if (!confirm(msg)) { input.checked = !enabled; return; }
        input.disabled = true;
        fetch('/ff/manager/approval/toggle', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({jsonrpc: '2.0', method: 'call', params: {enabled: enabled}})
        })
        .then(function(res) { return res.json(); })
        .then(function(data) {
            var res = data.result || {};
            if (res.status === 'success') {
                FFM.showToast(res.message, 'success');
                setTimeout(function() { window.location.href = '/ff/manager'; }, 600);
            } else {
                input.checked = !enabled;
                input.disabled = false;
                FFM.showToast(res.message || 'Could not change the setting.', 'error');
            }
        })
        .catch(function() {
            input.checked = !enabled;
            input.disabled = false;
            FFM.showToast('Network error.', 'error');
        });
    };

    FFM.approveReport = function(reportId, btn) {
        if (!confirm('Are you sure you want to approve this daily report?')) return;
        var release = FFM.doubleTapGuard(btn, 'Approving...');
        fetch('/ff/manager/report/approve', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({jsonrpc: '2.0', method: 'call', params: {report_id: reportId}})
        })
        .then(function(res) { return res.json(); })
        .then(function(data) {
            release();
            var res = data.result || {};
            if (res.status === 'success') {
                FFM.showToast(res.message, 'success');
                setTimeout(function() { window.location.reload(); }, 600);
            } else {
                FFM.showToast(res.message || 'Approval failed.', 'error');
            }
        })
        .catch(function() {
            release();
            FFM.showToast('Network error.', 'error');
        });
    };

    FFM.rejectReport = function(reportId, btn) {
        var reason = prompt('Please enter reason for rejecting this daily report:');
        if (reason === null) return;
        var release = FFM.doubleTapGuard(btn, 'Rejecting...');
        fetch('/ff/manager/report/reject', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({jsonrpc: '2.0', method: 'call', params: {report_id: reportId, reason: reason}})
        })
        .then(function(res) { return res.json(); })
        .then(function(data) {
            release();
            var res = data.result || {};
            if (res.status === 'success') {
                FFM.showToast(res.message, 'info');
                setTimeout(function() { window.location.reload(); }, 600);
            } else {
                FFM.showToast(res.message || 'Rejection failed.', 'error');
            }
        })
        .catch(function() {
            release();
            FFM.showToast('Network error.', 'error');
        });
    };

    FFM.checkStatement = function(statementId, btn) {
        if (!confirm('Confirm verification and check for this monthly statement?')) return;
        var release = FFM.doubleTapGuard(btn, 'Checking...');
        fetch('/ff/manager/statement/check', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({jsonrpc: '2.0', method: 'call', params: {statement_id: statementId}})
        })
        .then(function(res) { return res.json(); })
        .then(function(data) {
            release();
            var res = data.result || {};
            if (res.status === 'success') {
                FFM.showToast(res.message, 'success');
                setTimeout(function() { window.location.reload(); }, 600);
            } else {
                FFM.showToast(res.message || 'Check failed.', 'error');
            }
        })
        .catch(function() {
            release();
            FFM.showToast('Network error.', 'error');
        });
    };

    // 7. System Admin Actions (Personnel CRUD, Password Reset, Territory/Branch CRUD, Demo Seeding)
    FFM.jsonRpcPost = function(url, params, btn, loadingText, reloadTab) {
        var release = FFM.doubleTapGuard(btn, loadingText || 'Saving...');
        fetch(url, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({jsonrpc: '2.0', method: 'call', params: params || {}})
        })
        .then(function(res) { return res.json(); })
        .then(function(data) {
            release();
            var res = data.result || {};
            if (res.status === 'success') {
                FFM.showToast(res.message || 'Saved successfully.', 'success');
                setTimeout(function() {
                    if (reloadTab) {
                        window.location.href = '/ff/manager?tab=' + reloadTab;
                    } else {
                        window.location.reload();
                    }
                }, 600);
            } else {
                FFM.showToast(res.message || 'Operation failed.', 'error');
            }
        })
        .catch(function() {
            release();
            FFM.showToast('Network error.', 'error');
        });
    };

    FFM.seedDemoData = function(btn) {
        if (!confirm('Seed complete demo data (RSM, ASM, Field Persons, Branches, Territories, Attendance, Visits, Reports & Monthly Statements)?')) return;
        FFM.jsonRpcPost('/ff/admin/seed_demo', {}, btn, 'Seeding Demo Data...', null);
    };

    // People & logins (management): RSM / ASM / Field Person with email + password
    FFM.checkedValues = function(containerId) {
        var box = document.getElementById(containerId);
        if (!box) return [];
        return Array.prototype.map.call(box.querySelectorAll('input[type="checkbox"]:checked'), function(el) {
            return parseInt(el.value, 10);
        });
    };

    FFM.setChecked = function(containerId, csv) {
        var wanted = (csv || '').split(',').filter(function(v) { return v; });
        var box = document.getElementById(containerId);
        if (!box) return;
        box.querySelectorAll('input[type="checkbox"]').forEach(function(el) {
            el.checked = wanted.indexOf(el.value) !== -1;
        });
    };

    FFM.filterChecklist = function(input, containerId) {
        var q = (input.value || '').trim().toLowerCase();
        var box = document.getElementById(containerId);
        if (!box) return;
        box.querySelectorAll('.ffm-check').forEach(function(label) {
            label.style.display = (!q || label.textContent.toLowerCase().indexOf(q) !== -1) ? '' : 'none';
        });
    };

    FFM.onPersonRoleChange = function() {
        // Field Person reports to an ASM (or RSM), ASM reports to an RSM, RSM to nobody
        var role = (document.getElementById('pf_role') || {}).value || 'fp';
        var allowed = {fp: ['asm', 'rsm'], asm: ['rsm'], rsm: []}[role];
        var select = document.getElementById('pf_parent');
        if (!select) return;
        select.querySelectorAll('option[data-role]').forEach(function(opt) {
            var ok = allowed.indexOf(opt.getAttribute('data-role')) !== -1;
            opt.hidden = !ok;
            opt.disabled = !ok;
            if (!ok && opt.selected) select.value = '';
        });
        select.querySelectorAll('optgroup').forEach(function(group) {
            group.hidden = allowed.indexOf(group.label.toLowerCase()) === -1;
        });
    };

    FFM.resetPersonForm = function() {
        ['pf_id', 'pf_branch', 'pf_name', 'pf_email', 'pf_password', 'pf_phone', 'pf_hq', 'pf_terr_filter'].forEach(function(id) {
            var el = document.getElementById(id);
            if (el) el.value = '';
        });
        document.getElementById('pf_role').value = 'fp';
        document.getElementById('pf_parent').value = '';
        FFM.setChecked('pf_territories', '');
        FFM.filterChecklist(document.getElementById('pf_terr_filter'), 'pf_territories');
        FFM.onPersonRoleChange();
        document.getElementById('pf_title').innerText = 'Add Person';
        document.getElementById('pf_password_req').style.display = '';
        document.getElementById('pf_password_hint').innerText = 'At least 6 characters.';
        document.getElementById('pf_deactivate').style.display = 'none';
    };

    FFM.editPersonFromBtn = function(btn) {
        if (!btn) return;
        if (typeof switchManagerTab === 'function') switchManagerTab('team');
        FFM.resetPersonForm();
        document.getElementById('pf_id').value = btn.getAttribute('data-id') || '';
        document.getElementById('pf_branch').value = btn.getAttribute('data-branch') || '';
        document.getElementById('pf_name').value = btn.getAttribute('data-name') || '';
        document.getElementById('pf_role').value = btn.getAttribute('data-role') || 'fp';
        FFM.onPersonRoleChange();
        document.getElementById('pf_parent').value = btn.getAttribute('data-parent') || '';
        document.getElementById('pf_email').value = btn.getAttribute('data-email') || '';
        document.getElementById('pf_phone').value = btn.getAttribute('data-phone') || '';
        document.getElementById('pf_hq').value = btn.getAttribute('data-hq') || '';
        FFM.setChecked('pf_territories', btn.getAttribute('data-territories'));
        document.getElementById('pf_title').innerText = 'Edit: ' + (btn.getAttribute('data-name') || '');
        document.getElementById('pf_password_req').style.display = 'none';
        document.getElementById('pf_password_hint').innerText = 'Leave blank to keep the current password.';
        document.getElementById('pf_deactivate').style.display = '';
        var card = document.getElementById('personFormCard');
        if (card && card.scrollIntoView) card.scrollIntoView({behavior: 'smooth', block: 'start'});
    };

    FFM.savePerson = function(btn) {
        var empId = document.getElementById('pf_id').value;
        var name = document.getElementById('pf_name').value.trim();
        var email = document.getElementById('pf_email').value.trim();
        var password = document.getElementById('pf_password').value;
        if (!name) {
            FFM.showToast('Please enter the full name.', 'error');
            return;
        }
        if (!email) {
            FFM.showToast('Please enter the email used to log in.', 'error');
            return;
        }
        if (!empId && password.length < 6) {
            FFM.showToast('Password must be at least 6 characters.', 'error');
            return;
        }
        var terrIds = FFM.checkedValues('pf_territories');
        if (!terrIds || !terrIds.length) {
            FFM.showToast('Please select at least one territory for this person.', 'error');
            return;
        }
        FFM.jsonRpcPost('/ff/admin/employee/save', {
            emp_id: empId || null,
            name: name,
            role: document.getElementById('pf_role').value,
            email: email,
            password: password,
            parent_id: document.getElementById('pf_parent').value || null,
            territory_ids: terrIds,
            branch_id: document.getElementById('pf_branch').value || null,
            phone: document.getElementById('pf_phone').value,
            hq: document.getElementById('pf_hq').value
        }, btn, 'Saving...', 'team');
    };

    FFM.deactivatePerson = function(btn) {
        var empId = document.getElementById('pf_id').value;
        if (!empId) return;
        if (!confirm('Deactivate this person? Their login will stop working.')) return;
        FFM.jsonRpcPost('/ff/admin/employee/delete', {emp_id: empId}, btn, 'Deactivating...', 'team');
    };

    // Territories (management): many RSMs / ASMs / Field Persons per territory
    FFM.resetTerritoryForm = function() {
        ['tf_id', 'tf_name', 'tf_branch', 'tf_filter'].forEach(function(id) {
            var el = document.getElementById(id);
            if (el) el.value = '';
        });
        FFM.setChecked('tf_members', '');
        FFM.filterChecklist(document.getElementById('tf_filter'), 'tf_members');
        document.getElementById('tf_title').innerText = 'Add Territory';
    };

    FFM.editTerritoryFromBtn = function(btn) {
        if (!btn) return;
        FFM.resetTerritoryForm();
        document.getElementById('tf_id').value = btn.getAttribute('data-id') || '';
        document.getElementById('tf_name').value = btn.getAttribute('data-name') || '';
        document.getElementById('tf_branch').value = btn.getAttribute('data-branch') || '';
        FFM.setChecked('tf_members', btn.getAttribute('data-members'));
        document.getElementById('tf_title').innerText = 'Edit Territory: ' + (btn.getAttribute('data-name') || '');
        var card = document.getElementById('territoryFormCard');
        if (card && card.scrollIntoView) card.scrollIntoView({behavior: 'smooth', block: 'start'});
    };

    FFM.saveTerritory = function(btn) {
        var name = document.getElementById('tf_name').value.trim();
        var branchId = document.getElementById('tf_branch').value;
        if (!name) {
            FFM.showToast('Please enter a territory name.', 'error');
            return;
        }
        if (!branchId) {
            FFM.showToast('Please select a Depot for this territory.', 'error');
            return;
        }
        FFM.jsonRpcPost('/ff/admin/territory/save', {
            territory_id: document.getElementById('tf_id').value || null,
            name: name,
            branch_id: branchId || null,
            member_ids: FFM.checkedValues('tf_members')
        }, btn, 'Saving...', 'territories');
    };

    FFM.deleteTerritory = function(terrId, btn) {
        if (!confirm('Are you sure you want to delete this territory?')) return;
        FFM.jsonRpcPost('/ff/admin/territory/delete', {territory_id: terrId}, btn, 'Deleting...', 'territories');
    };

    FFM.saveBranch = function(btn) {
        var branchId = (document.getElementById('adm_branch_id') || {}).value || '';
        var name = (document.getElementById('adm_branch_name') || {}).value || '';
        var code = (document.getElementById('adm_branch_code') || {}).value || '';
        if (!name.trim()) {
            FFM.showToast('Please enter a depot name.', 'error');
            return;
        }
        FFM.jsonRpcPost('/ff/admin/branch/save', {
            branch_id: branchId || null,
            name: name,
            code: code
        }, btn, 'Saving Depot...', 'territories');
    };

    FFM.editBranchFromBtn = function(btn) {
        if (!btn) return;
        document.getElementById('adm_branch_id').value = btn.getAttribute('data-id') || '';
        document.getElementById('adm_branch_name').value = btn.getAttribute('data-name') || '';
        document.getElementById('adm_branch_code').value = btn.getAttribute('data-code') || '';
        var titleEl = document.getElementById('adm_branch_form_title');
        if (titleEl) {
            titleEl.innerText = 'Edit Depot: ' + (btn.getAttribute('data-name') || '');
        }
        var card = document.getElementById('adminBranchFormCard');
        if (card && card.scrollIntoView) {
            card.scrollIntoView({behavior: 'smooth', block: 'start'});
        }
    };

    FFM.resetBranchForm = function() {
        document.getElementById('adm_branch_id').value = '';
        document.getElementById('adm_branch_name').value = '';
        document.getElementById('adm_branch_code').value = '';
        var titleEl = document.getElementById('adm_branch_form_title');
        if (titleEl) {
            titleEl.innerText = 'Depots Management';
        }
    };

    FFM.deleteBranch = function(branchId, btn) {
        if (!confirm('Are you sure you want to delete this depot?')) return;
        FFM.jsonRpcPost('/ff/admin/branch/delete', {branch_id: branchId}, btn, 'Deleting...', 'territories');
    };

    // Person picker: type a name, choose an existing person, open their report
    FFM.initPersonPickers = function() {
        document.querySelectorAll('.ffm-picker').forEach(function(root) {
            var people = [];
            try {
                people = JSON.parse(root.getAttribute('data-people') || '[]');
            } catch (e) {
                people = [];
            }
            var input = root.querySelector('.ffm-picker-input');
            var list = root.querySelector('.ffm-picker-list');
            if (!input || !list) return;

            function matchesFor(q) {
                q = (q || '').trim().toLowerCase();
                if (!q) return people.slice();
                return people.filter(function(p) {
                    return p.name.toLowerCase().indexOf(q) !== -1;
                });
            }

            function open(person) {
                var mode = root.getAttribute('data-mode') || 'daily';
                var url = '/ff/report/cards?report_type=individual&mode=' + encodeURIComponent(mode) +
                          '&employee_id=' + person.id;
                if (mode === 'monthly') {
                    url += '&period=' + encodeURIComponent(root.getAttribute('data-period') || 'current');
                } else if (root.getAttribute('data-date')) {
                    url += '&date=' + encodeURIComponent(root.getAttribute('data-date'));
                }
                window.location.href = url;
            }

            function render() {
                var matches = matchesFor(input.value).slice(0, 40);
                list.innerHTML = '';
                if (!matches.length) {
                    var empty = document.createElement('div');
                    empty.className = 'ffm-picker-empty';
                    empty.textContent = 'No person found with this name.';
                    list.appendChild(empty);
                }
                matches.forEach(function(p) {
                    var item = document.createElement('button');
                    item.type = 'button';
                    item.className = 'ffm-picker-item';
                    var nameEl = document.createElement('span');
                    nameEl.className = 'ffm-picker-name';
                    nameEl.textContent = p.name;
                    var metaEl = document.createElement('span');
                    metaEl.className = 'ffm-picker-meta';
                    metaEl.textContent = [p.role, p.territories].filter(function(v) { return v; }).join(' • ');
                    item.appendChild(nameEl);
                    item.appendChild(metaEl);
                    item.addEventListener('mousedown', function(ev) {
                        ev.preventDefault();
                        input.value = p.name;
                        list.style.display = 'none';
                        open(p);
                    });
                    list.appendChild(item);
                });
                list.style.display = 'block';
            }

            input.addEventListener('focus', render);
            input.addEventListener('input', render);
            input.addEventListener('blur', function() {
                setTimeout(function() { list.style.display = 'none'; }, 150);
            });
            input.addEventListener('keydown', function(ev) {
                if (ev.key !== 'Enter') return;
                ev.preventDefault();
                var q = input.value.trim().toLowerCase();
                var exact = people.filter(function(p) { return p.name.toLowerCase() === q; });
                var matches = matchesFor(q);
                if (exact.length === 1) {
                    open(exact[0]);
                } else if (q && matches.length === 1) {
                    open(matches[0]);
                } else {
                    FFM.showToast(matches.length ? 'Several people match. Pick one from the list.' : 'No person found with this name.', 'error');
                }
            });
        });
    };

    document.addEventListener('DOMContentLoaded', FFM.initPersonPickers);
    document.addEventListener('DOMContentLoaded', FFM.showFlash);

    window.FFM = FFM;
})(window);
