package com.hermesandroid.relay.util

import android.content.Context
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.core.stringPreferencesKey
import com.hermesandroid.relay.data.relayDataStore
import kotlinx.coroutines.flow.first
import kotlinx.serialization.encodeToString
import kotlinx.serialization.json.Json

/**
 * Detects sensitive apps (banking, password managers, authentication) by
 * package-name prefix matching.
 *
 * When a sensitive app is in the foreground:
 *  - [com.hermesandroid.relay.bridge.BridgeStatusOverlay] auto-enables
 *    FLAG_SECURE to prevent screenshots / screen-recording of credentials.
 *  - [com.hermesandroid.relay.network.handlers.BridgeCommandHandler] blocks
 *    GET /clipboard (could exfiltrate copied passwords) with HTTP 403 and
 *    error_code = "sensitive_app_protection".
 *
 * # Two-tier prefix list
 *
 * 1. **Built-in prefixes** — ship with the app binary, cover the most common
 *    banking apps, password managers, and 2FA authenticators. Updated on each
 *    release.
 *
 * 2. **User prefixes** — editable via DataStore preferences. Stored as a
 *    JSON-encoded sorted list under `sensitive_app_user_prefixes`. Users can
 *    add their own package prefixes (e.g. a regional bank not in the built-in
 *    list).
 *
 * # Usage
 *
 * From a coroutine context (e.g. inside [BridgeCommandHandler.dispatch]):
 * ```kotlin
 * if (SensitiveAppDetector.isSensitiveApp(service, service.currentApp)) {
 *     // block clipboard, enable FLAG_SECURE
 * }
 * ```
 */
object SensitiveAppDetector {

    private const val TAG = "SensitiveAppDetector"

    private val KEY_USER_PREFIXES = stringPreferencesKey("sensitive_app_user_prefixes")

    private val json = Json {
        ignoreUnknownKeys = true
        encodeDefaults = true
    }

    /**
     * Built-in sensitive package prefixes.
     *
     * Covers the most common banking apps, password managers, and 2FA
     * authenticators across the US, UK, and generic Android system packages.
     * Ship with the binary; users cannot modify this set.
     */
    private val BUILTIN_SENSITIVE_PREFIXES: Set<String> = setOf(
        // ── System credential / auth ──────────────────────────────────
        "com.android.credentialmgr",
        "com.google.android.gms.auth",
        "com.samsung.android.auth",

        // ── Banking (US) ───────────────────────────────────────────────
        "com.chase.sig.android",
        "com.wf.wellsfargomobile",
        "com.bankofamerica",
        "com.usaa.mobile.android.usaa",
        "com.konylabs.capitalone",
        "com.americanexpress.android.acctsvcs.us",
        "com.discoverfinancial.mobile",
        "com.infonow.bofa",
        "com.citi.citimobile",

        // ── Banking (UK / EU) ─────────────────────────────────────────
        "uk.co.hsbc.hsbcukmobilebanking",
        "com.barclays.android.barclaysmobilebanking",
        "com.monzo.android",
        "co.uk.getmondo",
        "co.revolut.app",
        "com.starlingbank.android",
        "com.lloydsbank",
        "com.rbs.mobile.android",
        "com.natwest",
        "com.santander",

        // ── Payments / crypto ─────────────────────────────────────────
        "com.venmo",
        "com.squareup.cash",
        "com.paypal.android.p2pmobile",
        "com.coinbase.android",
        "co.mona.android",
        "com.kraken",

        // ── Password managers ─────────────────────────────────────────
        "com.lastpass.lpandroid",
        "com.dashlane",
        "com.agilebits.onepassword",
        "com.x8bit.bitwarden",
        "com.keepersecurity.passwordmanager",
        "com.bitwarden.authenticator",
        "com.enzopc.1password",

        // ── 2FA / Auth apps ───────────────────────────────────────────
        "com.google.android.apps.authenticator2",
        "com.authy.authy",
        "com.duosecurity.duomobile",
        "com.microsoft.azure.authenticator",
        "com.yubico.yubioath",
    )

    /**
     * Returns `true` if [packageName] matches any built-in or user-defined
     * sensitive prefix.
     *
     * [context] is needed to read the user-defined prefix list from DataStore.
     * DataStore reads are served from an in-memory cache after the first load,
     * so this is fast on repeated calls.
     *
     * Blank or null package names return false (no foreground app detected
     * yet, so no protection to apply).
     */
    suspend fun isSensitiveApp(context: Context, packageName: String?): Boolean {
        if (packageName.isNullOrBlank()) return false

        // Check built-in prefixes first (fast path — no I/O)
        if (BUILTIN_SENSITIVE_PREFIXES.any { packageName.startsWith(it) }) {
            android.util.Log.d(TAG, "Sensitive app detected (builtin): $packageName")
            return true
        }

        // Check user-defined prefixes (DataStore-backed, cached in memory)
        val userPrefixes = loadUserPrefixes(context)
        return if (userPrefixes.any { packageName.startsWith(it) }) {
            android.util.Log.d(TAG, "Sensitive app detected (user): $packageName")
            true
        } else {
            false
        }
    }

    // ── User-prefix DataStore API ────────────────────────────────────────

    /**
     * Load the user-defined prefix set from DataStore. Safe to call
     * repeatedly — DataStore serves from in-memory cache after first load.
     */
    suspend fun loadUserPrefixes(context: Context): Set<String> {
        return context.relayDataStore.data.map { prefs ->
            val raw = prefs[KEY_USER_PREFIXES]
            if (raw.isNullOrBlank()) {
                emptySet()
            } else {
                runCatching { json.decodeFromString<List<String>>(raw).toSet() }
                    .getOrDefault(emptySet())
            }
        }.first()
    }

    /**
     * Set the full user-defined prefix list. Replaces existing user entries
     * with [prefixes].
     */
    suspend fun setUserPrefixes(context: Context, prefixes: Set<String>) {
        context.relayDataStore.edit { prefs ->
            val sorted = prefixes.filter { it.isNotBlank() }.toList().sorted()
            prefs[KEY_USER_PREFIXES] = json.encodeToString(sorted)
        }
    }

    /**
     * Add a single prefix to the user-defined set.
     */
    suspend fun addUserPrefix(context: Context, prefix: String) {
        val trimmed = prefix.trim()
        if (trimmed.isEmpty()) return
        context.relayDataStore.edit { prefs ->
            val raw = prefs[KEY_USER_PREFIXES]
            val current = if (raw.isNullOrBlank()) emptySet()
            else runCatching { json.decodeFromString<List<String>>(raw).toSet() }
                .getOrDefault(emptySet())
            val next = (current + trimmed).toList().sorted()
            prefs[KEY_USER_PREFIXES] = json.encodeToString(next)
        }
    }

    /**
     * Remove a single prefix from the user-defined set.
     */
    suspend fun removeUserPrefix(context: Context, prefix: String) {
        val trimmed = prefix.trim()
        if (trimmed.isEmpty()) return
        context.relayDataStore.edit { prefs ->
            val raw = prefs[KEY_USER_PREFIXES]
            val current = if (raw.isNullOrBlank()) emptySet()
            else runCatching { json.decodeFromString<List<String>>(raw).toSet() }
                .getOrDefault(emptySet())
            val next = (current - trimmed).toList().sorted()
            prefs[KEY_USER_PREFIXES] = json.encodeToString(next)
        }
    }

    /**
     * Clear all user-defined prefixes. Built-in prefixes remain active.
     */
    suspend fun clearUserPrefixes(context: Context) {
        context.relayDataStore.edit { prefs ->
            prefs[KEY_USER_PREFIXES] = json.encodeToString(emptyList<String>())
        }
    }
}
