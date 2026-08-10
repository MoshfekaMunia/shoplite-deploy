# ShopLite design decisions

## Why PostgreSQL, MongoDB, and Redis?

Users and orders have stable fields and benefit from relational constraints, so
PostgreSQL is a straightforward choice. Product attributes can vary by product
type, which makes MongoDB's document model convenient for this exercise. The
notifications are short-lived records accessed by user ID, so Redis lists with
an expiry provide a deliberately simple implementation.

## Why RabbitMQ instead of Kafka?

ShopLite needs one small work queue, not a large event-streaming platform.
RabbitMQ is quick to run locally, supports durable queues and acknowledgements,
and clearly demonstrates asynchronous delivery. Kafka would become reasonable
if the organization needed retained event history, replay by several consumer
groups, or much higher event throughput.

## Why are user and catalog checks synchronous?

An order should not be accepted for a missing user or product, and the product
price is needed to calculate the order total. `order-service` therefore waits
for those two REST responses, with a three-second timeout. A notification is
not required to complete the customer's order, so it is sent asynchronously.

## Why does every service own its database?

Database ownership prevents one service from depending on another service's
tables and allows each service to evolve independently. The cost is additional
operational work: more database instances, credentials, backups, migrations,
monitoring, and cross-service consistency problems.

## What would change in production?

First, databases would use managed services or properly configured StatefulSets
instead of simple Deployments. Second, credentials would come from a secret
manager rather than a repository-managed Kubernetes Secret. Third, the system
would add authentication, authorization, schema migrations, structured
observability, dead-letter handling, idempotent message processing, and a
transactional outbox so an order and its event cannot become inconsistent.

