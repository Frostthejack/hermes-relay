package com.hermesandroid.relay.bridge

import android.util.Log
import java.util.concurrent.ConcurrentHashMap

/**
 * Per-path rate limiter for bridge commands.
 *
 * Enforces sliding-window rate limits on accessibility actions to prevent
 * a compromised server or looping LLM from firing thousands of taps, swipes,
 * or SMS sends per minute.
 *
 * Also detects simple automated patterns: if the last 5 timestamps for a
 * given path have near-identical intervals (< 50ms standard deviation),
 * the request is rejected as bot-like even if it's under the count cap.
 *
 * Called from BridgeCommandHandler.dispatch() after the blocklist check but
 * before the safety confirmation modal. If tryAcquire returns false the
 * handler responds with HTTP 429 and error_code = "rate_limited".
 */
class ActionRateLimiter {

    data class RateLimit(
        val maxActions: Int,
        val windowMs: Long,
        val description: String,
    )

    private val limits = mapOf(
        "/tap" to RateLimit(maxActions = 30, windowMs = 10_000, description = "30 taps/10s"),
        "/tap_text" to RateLimit(maxActions = 10, windowMs = 10_000, description = "10 tap_text/10s"),
        "/type" to RateLimit(maxActions = 10, windowMs = 10_000, description = "10 type/10s"),
        "/swipe" to RateLimit(maxActions = 20, windowMs = 10_000, description = "20 swipes/10s"),
        "/send_sms" to RateLimit(maxActions = 3, windowMs = 60_000, description = "3 SMS/min"),
        "/call" to RateLimit(maxActions = 2, windowMs = 60_000, description = "2 calls/min"),
        "/screen" to RateLimit(maxActions = 10, windowMs = 10_000, description = "10 screen reads/10s"),
        "/screenshot" to RateLimit(maxActions = 5, windowMs = 10_000, description = "5 screenshots/10s"),
    )

    private val actionTimestamps = ConcurrentHashMap<String, MutableList<Long>>()

    /**
     * Returns true if the action is allowed, false if rate-limited.
     *
     * Paths not present in the limits map pass through unthrottled
     * (no limit configured = allow). This covers internal / utility
     * paths like /ping, /setup, /events, etc.
     */
    fun tryAcquire(path: String): Boolean {
        val limit = limits[path] ?: return true // no limit configured → allow

        val now = System.currentTimeMillis()
        val timestamps = actionTimestamps.getOrPut(path) { mutableListOf() }

        synchronized(timestamps) {
            // Prune entries outside the sliding window
            timestamps.removeAll { now - it > limit.windowMs }

            // Check count cap
            if (timestamps.size >= limit.maxActions) {
                Log.w(
                    TAG,
                    "Rate limited $path: ${timestamps.size}/${limit.maxActions} in ${limit.windowMs}ms",
                )
                return false
            }

            // Detect automated patterns: if last 5 actions had
            // near-identical intervals (< 50ms std dev), flag as bot-like
            if (timestamps.size >= 5) {
                val recent = timestamps.takeLast(5)
                val intervals = recent.zipWithNext { a, b -> b - a }
                val avgInterval = intervals.average()
                val variance = intervals
                    .map { d -> (d - avgInterval).let { diff -> diff * diff } }
                    .average()
                if (variance < AUTOMATED_PATTERN_VARIANCE_THRESHOLD_MS2) {
                    Log.w(
                        TAG,
                        "Automated pattern detected for $path: variance=$variance " +
                            "(threshold=$AUTOMATED_PATTERN_VARIANCE_THRESHOLD_MS2)",
                    )
                    return false
                }
            }

            timestamps.add(now)
            return true
        }
    }

    companion object {
        private const val TAG = "ActionRateLimiter"

        /** Variance threshold in ms² — std dev < 50ms → variance < 2500 */
        private const val AUTOMATED_PATTERN_VARIANCE_THRESHOLD_MS2 = 2500.0
    }
}
