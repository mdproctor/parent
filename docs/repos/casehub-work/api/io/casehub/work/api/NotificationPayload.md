# io.casehub.work.api.NotificationPayload

**Package:** `io.casehub.work.api`

**Kind:** `record`

Payload passed to `NotificationChannel.send` for each matched rule.

<p>
Contains both the triggering lifecycle event and the matching rule, so
channel implementations can access WorkItem fields and rule-specific config
(target URL, HMAC secret, etc.) without additional lookups.

## Fields

### `channelType` (`java.lang.String`)

### `event` (`io.casehub.work.api.WorkItemEvent`)

### `ruleId` (`java.util.UUID`)

### `secret` (`java.lang.String`)

### `targetUrl` (`java.lang.String`)

### `types` (`java.lang.String`)

## Record Components

### `channelType` (`java.lang.String`)

the channel type string (e.g. `"slack"`)

### `event` (`io.casehub.work.api.WorkItemEvent`)

the lifecycle event that triggered this notification

### `ruleId` (`java.util.UUID`)

the UUID of the matched rule

### `secret` (`java.lang.String`)

optional HMAC secret for signed channels; null if not configured

### `targetUrl` (`java.lang.String`)

the destination URL or address for this notification

### `types` (`java.lang.String`)

the type filter from the rule; null means all types matched

## Constructors

### `public NotificationPayload(io.casehub.work.api.WorkItemEvent event, java.util.UUID ruleId, java.lang.String channelType, java.lang.String targetUrl, java.lang.String secret, java.lang.String types)`

#### Parameters

- `event` (`io.casehub.work.api.WorkItemEvent`)
- `ruleId` (`java.util.UUID`)
- `channelType` (`java.lang.String`)
- `targetUrl` (`java.lang.String`)
- `secret` (`java.lang.String`)
- `types` (`java.lang.String`)

## Methods

### `public java.lang.String channelType()`

### `public final boolean equals(java.lang.Object o)`

#### Parameters

- `o` (`java.lang.Object`)

### `public io.casehub.work.api.WorkItemEvent event()`

### `public final int hashCode()`

### `public java.util.UUID ruleId()`

### `public java.lang.String secret()`

### `public java.lang.String targetUrl()`

### `public final java.lang.String toString()`

### `public java.lang.String types()`
