// Conventional Commits that name the plan item (plan 4.1, CLAUDE.md rule 8):
// a task (T26), a change request (CR-002), a gate (gate M1) or a spec/plan sync (sync spec v2).
const PLAN_ITEM = /\b(T\d{2}|CR-\d{3}|gate M\d|sync (spec|plan) v\d+)\b/;

export default {
  extends: ['@commitlint/config-conventional'],
  plugins: [
    {
      rules: {
        'subject-references-plan-item': ({ subject }) => [
          PLAN_ITEM.test(subject ?? ''),
          'subject must name a task (T26), change request (CR-002), gate (gate M1) or sync (sync spec v2)',
        ],
      },
    },
  ],
  rules: {
    'subject-references-plan-item': [2, 'always'],
    // Task IDs start the subject ("T26 cycle engine"), which reads as sentence case.
    'subject-case': [0],
  },
};
