# Private mobile access

Approved approach: run an independent single-owner Ledger on an always-on private server. iPhone and Windows open the same HTTPS origin and therefore the same records. The existing local Windows installation remains intact until its owner confirms whether records need migration.

## Implementation

- Keep financial data, owner authentication, bank configuration and optional worker state separate from every other instance.
- Use a dedicated private-network node/address for this instance. Do not publish a router port or enable public Funnel access. Sharing that node must not expose unrelated server services.
- Preserve the existing responsive UI. Add local PNG home-screen icons and consistent warm-paper manifest metadata; provide Safari Add to Home Screen instructions.
- Keep API responses uncached. The home-screen app requires network access to the server; this change does not implement offline writes or database synchronization.
- Windows users open the same hosted address. The earlier local desktop launcher remains a separate data source; do not imply that it automatically syncs.
- If existing local records need migration, stop local writes, make a protected consistent backup, transfer privately, validate and restore into the independent instance before switching devices. Never commit the backup or account configuration.
- Initial owner setup retains the localhost-only restriction. Arrange an authorized loopback forward or migrate the existing owner verifier; do not weaken authentication for remote setup.

## Validation

Verify PNG dimensions, manifest references, HTML metadata and unchanged API protection. Check the new container's data mount, restart policy, loopback publication and private HTTPS health. Confirm the original Ledger and other private routes remain unchanged. Verify actual iPhone installation with the owner when the device and private-network login are available; browser emulation alone does not establish native iOS behavior.

No personal names, addresses, account handles, device identities or credentials belong in this document or source. Deployment-specific values stay in private server configuration.
