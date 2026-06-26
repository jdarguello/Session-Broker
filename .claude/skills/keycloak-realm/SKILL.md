---
name: keycloak-realm
description: Safely change and validate the Keycloak `enterpriseclaw` realm (groups, roles, clients, identity providers, users) — which is managed declaratively by keycloak-config-cli and reconciled by Argo CD. Use whenever editing the realm catalog, before committing/pushing.
---

# Changing the Keycloak realm safely

The `enterpriseclaw` realm is **declarative**: it lives inlined in
[`gitops/keycloak/values.yaml`](../../../gitops/keycloak/values.yaml) under
`keycloakConfigCli.configuration."enterpriseclaw.yaml"`, and the Bitnami chart's
bundled **keycloak-config-cli** applies it as an **in-cluster post-upgrade Helm
hook Job** on every Argo CD sync. There is **no** manual Admin-UI / kcadm step.

A bad import can silently break the live realm (the demo runs on it), so **always
validate with a one-off Job before pushing**.

## Hard rules (these have bitten us)

1. **Additive only.** The Job runs with `IMPORT_MANAGED_*=no-delete`. Keep it that
   way — `full` mode would prune Keycloak built-ins (`account`, `broker`,
   `realm-management`, …) and any client not in the file.
2. **No `$(env:...)` in realm comments.** Substitution runs over the *whole file
   including comments*; a literal `$(env:...)` placeholder → `Cannot resolve
   variable 'env:...'` and the import aborts (before applying anything — so it
   fails safe). Write "env substitution" in prose.
3. **Secrets are never committed.** Use `$(env:VAR)` referencing keys in the
   pre-created `keycloak-realm-secrets` Secret (namespace `keycloak`):
   `SESSION_BROKER_CLIENT_SECRET` (MUST equal `session-broker-secret/keycloak-client-secret`),
   `GOOGLE_CLIENT_SECRET`, `ALICE_PASSWORD`. Keycloak **masks** IdP/client secrets
   on read, so they can't be recovered from the cluster — supply out-of-band.
4. Realm is **`enterpriseclaw`**. Cluster access is `ssh controlplane kubectl …`
   (no kubectl on the Mac; **no `sudo`** on the node — it's blocked).

## Authorization model (what the realm encodes)

Claims-only: the broker carries permissions in the token; downstream agents
enforce. Groups (`/engineering` → `/engineering/seniors`) + realm roles
(`agent-user`, composite `senior-engineer`) + per-agent `bearerOnly` clients
(`issue-tracker`, `infra-provisioner`) holding client roles. Full table in
[`docs/docs/architecture/dapr-keycloak.mdx`](../../../docs/docs/architecture/dapr-keycloak.mdx).

## Workflow

1. **Edit** the inlined realm in `gitops/keycloak/values.yaml`.
2. **Extract + lint** the inner realm (the Mac has `ruby`/psych, not pyyaml):
   ```bash
   ruby -ryaml -e 'v=YAML.load_file("gitops/keycloak/values.yaml"); \
     inner=v["keycloakConfigCli"]["configuration"]["enterpriseclaw.yaml"]; \
     File.write("/tmp/realm.yaml", inner); YAML.load(inner); \
     puts "OK; refs="+inner.scan(/\$\([^)]*\)/).uniq.join(",")'
   ```
   Confirm only the expected `$(env:…)` refs appear (no stray `$(env:...)`).
3. **Validate on-cluster** with a one-off Job (see template below). It applies to
   the *live* realm additively — same operation Argo will run, just observed
   directly so you catch errors first.
4. **Verify claims** if relevant: run the broker flow and decode the access token
   (`scratchpad/verify.py` for alice; `resolve_check.py` for a cached user) — they
   print `groups` / `realm_access.roles` / `resource_access.<agent>.roles`.
   Never print token *values*.
5. **Commit + push** (`docs/` first if behavior changed). Argo auto-syncs and runs
   the chart hook.
6. **Confirm the real path:**
   ```bash
   ssh controlplane 'kubectl annotate application keycloak -n argocd argocd.argoproj.io/refresh=hard --overwrite'
   # then watch for Synced+Healthy on the new revision and the completed hook:
   ssh controlplane 'kubectl get events -n keycloak --sort-by=.lastTimestamp | grep keycloak-config-cli | tail'
   ```
   The hook job (`keycloak-keycloak-config-cli`) auto-prunes on success
   (`hook-delete-policy: hook-succeeded`); the event log "Job completed" + the app
   `Synced | Healthy` on the new revision is the success signal.

## One-off validation Job (additive, mirrors the committed extraEnvVars)

`scp /tmp/realm.yaml controlplane:/tmp/realm.yaml`, then on the controlplane:

```bash
kubectl create configmap realm-validate -n keycloak \
  --from-file=enterpriseclaw.yaml=/tmp/realm.yaml --dry-run=client -o yaml | kubectl apply -f -
kubectl delete job realm-validate -n keycloak --ignore-not-found
cat <<'EOF' | kubectl apply -f -
apiVersion: batch/v1
kind: Job
metadata: { name: realm-validate, namespace: keycloak }
spec:
  backoffLimit: 0
  ttlSecondsAfterFinished: 900
  template:
    spec:
      restartPolicy: Never
      containers:
        - name: kc-config-cli
          image: docker.io/bitnamilegacy/keycloak-config-cli:6.1.6-debian-12-r3
          env:
            - { name: KEYCLOAK_URL, value: "http://keycloak.keycloak.svc.cluster.local" }
            - { name: KEYCLOAK_USER, value: "admin" }
            - { name: KEYCLOAK_PASSWORD, valueFrom: { secretKeyRef: { name: keycloak-admin-secret, key: admin-password } } }
            - { name: KEYCLOAK_REALM, value: "master" }
            - { name: IMPORT_FILES_LOCATIONS, value: "/config/*.yaml" }
            - { name: IMPORT_VARSUBSTITUTION_ENABLED, value: "true" }
            - { name: IMPORT_MANAGED_CLIENT, value: "no-delete" }
            - { name: IMPORT_MANAGED_ROLE, value: "no-delete" }
            - { name: IMPORT_MANAGED_CLIENTSCOPE, value: "no-delete" }
            - { name: IMPORT_MANAGED_GROUP, value: "no-delete" }
            - { name: IMPORT_MANAGED_IDENTITYPROVIDER, value: "no-delete" }
            - { name: IMPORT_MANAGED_IDENTITYPROVIDERMAPPER, value: "no-delete" }
          envFrom: [ { secretRef: { name: keycloak-realm-secrets } } ]
          volumeMounts: [ { name: cfg, mountPath: /config } ]
      volumes: [ { name: cfg, configMap: { name: realm-validate } } ]
EOF
kubectl wait --for=condition=complete job/realm-validate -n keycloak --timeout=240s
kubectl logs job/realm-validate -n keycloak --tail=40   # expect "keycloak-config-cli ran in ..."
```

A clean run logs `Importing file ...` then `keycloak-config-cli ran in 00:0X`.
Any error (bad mapper id, unresolved var, schema) shows as `ERROR ...` and a
`failed` Job — fix the realm file and re-run before pushing. Clean up the
`realm-validate` Job/ConfigMap afterward (deletes need user approval).
