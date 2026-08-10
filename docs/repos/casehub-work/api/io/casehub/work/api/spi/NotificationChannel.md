# io.casehub.work.api.spi.NotificationChannel

**Package:** `io.casehub.work.api.spi`

**Kind:** `interface`

SPI for outbound notification delivery.

<p>
Implementations are CDI `@ApplicationScoped` beans discovered at startup.
The `.channelType()` string is matched against
`WorkItemNotificationRule.channelType` in the database to route each rule
to the correct channel implementation.

<p>
Built-in implementations: `"http-webhook"`, `"slack"`, `"teams"`.
Custom implementations: provide a CDI bean with any `channelType()` string,
persist rules with that type, and it will be called automatically.

<p>
`send()` is called from a worker thread — it must not assume any active
JTA transaction. Implementations should handle delivery failures gracefully
(log and continue) to avoid disrupting the WorkItem lifecycle.

## Methods

### `public abstract java.lang.String channelType()`

Identifies this channel — matched against `WorkItemNotificationRule.channelType`.

#### Returns

the channel type string, e.g. `"http-webhook"`, `"slack"`

### `public abstract void send(io.casehub.work.api.NotificationPayload payload)`

Send a notification for the given payload.

<p>
Called on a worker thread after the WorkItem lifecycle event has been committed.
Implementations must not throw unchecked exceptions — log failures and return.

#### Parameters

- `payload` (`io.casehub.work.api.NotificationPayload`) — the notification payload containing the lifecycle event and matched rule
