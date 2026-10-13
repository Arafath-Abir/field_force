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

    FFM.saveEmployee = function(btn) {
        var empId = (document.getElementById('adm_emp_id') || {}).value || '';
        var name = (document.getElementById('adm_emp_name') || {}).value || '';
        var role = (document.getElementById('adm_emp_role') || {}).value || 'fp';
        var login = (document.getElementById('adm_emp_login') || {}).value || '';
        var password = (document.getElementById('adm_emp_password') || {}).value || '';
        var parentId = (document.getElementById('adm_emp_parent_id') || {}).value || '';
        var branchId = (document.getElementById('adm_emp_branch_id') || {}).value || '';
        var hq = (document.getElementById('adm_emp_hq') || {}).value || '';
        var phone = (document.getElementById('adm_emp_phone') || {}).value || '';

        if (!name.trim()) {
            FFM.showToast('Please enter the personnel full name.', 'error');
            return;
        }
        if (!empId && !login.trim()) {
            FFM.showToast('Please enter a login username for the new personnel.', 'error');
            return;
        }

        FFM.jsonRpcPost('/ff/admin/employee/save', {
            emp_id: empId || null,
            name: name,
            role: role,
            login: login,
            password: password,
            parent_id: parentId || null,
            branch_id: branchId || null,
            hq: hq,
            phone: phone
        }, btn, 'Saving Personnel...', 'team');
    };

    FFM.editEmployeeFromBtn = function(btn) {
        if (!btn) return;
        document.getElementById('adm_emp_id').value = btn.getAttribute('data-id') || '';
        document.getElementById('adm_emp_name').value = btn.getAttribute('data-name') || '';
        document.getElementById('adm_emp_role').value = btn.getAttribute('data-role') || 'fp';
        document.getElementById('adm_emp_login').value = btn.getAttribute('data-login') || '';
        document.getElementById('adm_emp_password').value = '';
        document.getElementById('adm_emp_parent_id').value = btn.getAttribute('data-parent') || '';
        document.getElementById('adm_emp_branch_id').value = btn.getAttribute('data-branch') || '';
        document.getElementById('adm_emp_hq').value = btn.getAttribute('data-hq') || '';
        document.getElementById('adm_emp_phone').value = btn.getAttribute('data-phone') || '';
        var titleEl = document.getElementById('adm_emp_form_title');
        if (titleEl) {
            titleEl.innerText = 'Edit Personnel: ' + (btn.getAttribute('data-name') || '');
        }
        var card = document.getElementById('adminEmployeeFormCard');
        if (card && card.scrollIntoView) {
            card.scrollIntoView({behavior: 'smooth', block: 'start'});
        }
    };

    FFM.resetEmployeeForm = function() {
        document.getElementById('adm_emp_id').value = '';
        document.getElementById('adm_emp_name').value = '';
        document.getElementById('adm_emp_role').value = 'fp';
        document.getElementById('adm_emp_login').value = '';
        document.getElementById('adm_emp_password').value = '';
        document.getElementById('adm_emp_parent_id').value = '';
        document.getElementById('adm_emp_branch_id').value = '';
        document.getElementById('adm_emp_hq').value = '';
        document.getElementById('adm_emp_phone').value = '';
        var titleEl = document.getElementById('adm_emp_form_title');
        if (titleEl) {
            titleEl.innerText = 'Add New Personnel (RSM / ASM / Field Person)';
        }
    };

    FFM.deleteEmployee = function(empId, btn) {
        if (!confirm('Are you sure you want to remove/deactivate this personnel record?')) return;
        FFM.jsonRpcPost('/ff/admin/employee/delete', {emp_id: empId}, btn, 'Removing...', 'team');
    };

    FFM.openPasswordResetFromBtn = function(btn) {
        if (!btn) return;
        var empId = btn.getAttribute('data-id') || '';
        var selectEl = document.getElementById('adm_pwd_emp_id');
        var pwdInput = document.getElementById('adm_pwd_new');
        if (selectEl) selectEl.value = empId;
        var card = document.getElementById('adminPasswordResetCard');
        if (card && card.scrollIntoView) {
            card.scrollIntoView({behavior: 'smooth', block: 'center'});
        }
        if (pwdInput) {
            pwdInput.value = '';
            setTimeout(function() { pwdInput.focus(); }, 250);
        }
    };

    FFM.submitPasswordReset = function(btn) {
        var empId = (document.getElementById('adm_pwd_emp_id') || {}).value || '';
        var newPassword = (document.getElementById('adm_pwd_new') || {}).value || '';
        if (!empId) {
            FFM.showToast('Please select a personnel account first.', 'error');
            return;
        }
        if (!newPassword.trim()) {
            FFM.showToast('Please enter a new password.', 'error');
            return;
        }
        FFM.jsonRpcPost('/ff/admin/employee/reset_password', {
            emp_id: empId,
            new_password: newPassword
        }, btn, 'Updating Password...', 'team');
    };

    FFM.saveTerritory = function(btn) {
        var terrId = (document.getElementById('adm_terr_id') || {}).value || '';
        var name = (document.getElementById('adm_terr_name') || {}).value || '';
        var branchId = (document.getElementById('adm_terr_branch_id') || {}).value || '';
        var managerId = (document.getElementById('adm_terr_manager_id') || {}).value || '';
        var fpId = (document.getElementById('adm_terr_fp_id') || {}).value || '';
        if (!name.trim()) {
            FFM.showToast('Please enter a territory name.', 'error');
            return;
        }
        FFM.jsonRpcPost('/ff/admin/territory/save', {
            territory_id: terrId || null,
            name: name,
            branch_id: branchId || null,
            manager_id: managerId || null,
            field_person_id: fpId || null
        }, btn, 'Saving Territory...', 'territories');
    };

    FFM.editTerritoryFromBtn = function(btn) {
        if (!btn) return;
        document.getElementById('adm_terr_id').value = btn.getAttribute('data-id') || '';
        document.getElementById('adm_terr_name').value = btn.getAttribute('data-name') || '';
        document.getElementById('adm_terr_branch_id').value = btn.getAttribute('data-branch') || '';
        document.getElementById('adm_terr_manager_id').value = btn.getAttribute('data-manager') || '';
        document.getElementById('adm_terr_fp_id').value = btn.getAttribute('data-fp') || '';
        var titleEl = document.getElementById('adm_terr_form_title');
        if (titleEl) {
            titleEl.innerText = 'Edit Territory: ' + (btn.getAttribute('data-name') || '');
        }
        var card = document.getElementById('adminTerritoryFormCard');
        if (card && card.scrollIntoView) {
            card.scrollIntoView({behavior: 'smooth', block: 'start'});
        }
    };

    FFM.resetTerritoryForm = function() {
        document.getElementById('adm_terr_id').value = '';
        document.getElementById('adm_terr_name').value = '';
        document.getElementById('adm_terr_branch_id').value = '';
        document.getElementById('adm_terr_manager_id').value = '';
        document.getElementById('adm_terr_fp_id').value = '';
        var titleEl = document.getElementById('adm_terr_form_title');
        if (titleEl) {
            titleEl.innerText = 'Add / Edit Territory';
        }
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
            FFM.showToast('Please enter a branch name.', 'error');
            return;
        }
        FFM.jsonRpcPost('/ff/admin/branch/save', {
            branch_id: branchId || null,
            name: name,
            code: code
        }, btn, 'Saving Branch...', 'territories');
    };

    FFM.editBranchFromBtn = function(btn) {
        if (!btn) return;
        document.getElementById('adm_branch_id').value = btn.getAttribute('data-id') || '';
        document.getElementById('adm_branch_name').value = btn.getAttribute('data-name') || '';
        document.getElementById('adm_branch_code').value = btn.getAttribute('data-code') || '';
        var titleEl = document.getElementById('adm_branch_form_title');
        if (titleEl) {
            titleEl.innerText = 'Edit Branch: ' + (btn.getAttribute('data-name') || '');
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
            titleEl.innerText = 'Branches Management';
        }
    };

    FFM.deleteBranch = function(branchId, btn) {
        if (!confirm('Are you sure you want to delete this branch?')) return;
        FFM.jsonRpcPost('/ff/admin/branch/delete', {branch_id: branchId}, btn, 'Deleting...', 'territories');
    };

    window.FFM = FFM;
})(window);
