import { afterEach } from 'vitest'
import { cleanup } from '@testing-library/react'
import '@testing-library/jest-dom/vitest'

// Testing Library's DOM cleanup between tests is opt-in unless vitest's
// `globals` mode registers `afterEach` for it automatically — this project
// does not turn `globals` on, so it is wired explicitly. Without this, a
// second test's render leaves the first test's DOM in place and every
// `getByText` that matches more than one section starts failing for a reason
// that has nothing to do with the component under test.
afterEach(() => {
  cleanup()
})
