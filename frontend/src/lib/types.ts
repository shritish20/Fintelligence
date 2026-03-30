/**
 * src/lib/types.ts
 *
 * Single source of truth for Volguard types lives in:
 *   src/modules/volguard/lib/types.ts
 *
 * This file re-exports everything from there so that
 * global imports (@/lib/types) and module-relative imports
 * (../lib/types) both point to the same definitions.
 * Update types in modules/volguard/lib/types.ts only.
 */
export * from '@/modules/volguard/lib/types'
