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
        buttonElement.setAttribute('data-original-text', originalText);
        buttonElement.innerHTML = loadingText || 'অনুগ্রহ করে অপেক্ষা করুন... (Processing)';

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
            onError(new Error('এই ব্রাউজারে GPS Geolocation সমর্থিত নয়। (Geolocation not supported)'));
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
                var msg = 'অবস্থান পাওয়া যায়নি। (Unable to retrieve location)';
                if (err.code === 1) {
                    msg = 'GPS অনুমতির প্রয়োজন। ব্রাউজার সেটিংসে লোকেশন অন করুন। (Permission denied)';
                } else if (err.code === 2) {
                    msg = 'নেটওয়ার্ক বা জিপিএস সংকেত পাওয়া যায়নি। (Position unavailable)';
                } else if (err.code === 3) {
                    msg = 'জিপিএস সংযোগ সময়োত্তীর্ণ হয়েছে। আবার চেষ্টা করুন। (Timeout)';
                }
                onError(new Error(msg));
            },
            options
        );
    };

    window.FFM = FFM;
})(window);
