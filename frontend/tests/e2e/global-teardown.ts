import { execSync } from 'child_process';

/**
 * Playwright global teardown — cleanup e2etest users and test data from database.
 * Runs after all tests complete.
 */
export default function globalTeardown() {
  // Step 1: Clean up events, contracts and blog posts created by test accounts during E2E runs
  try {
    const dataResult = execSync(
      `python3 /opt/parahub/manage.py shell -c "
from identity.models import Contract
from geo.models import Event
from cms.models import Post
e_count, _ = Event.objects.filter(organizer__account__is_test=True, title__startswith='E2E-').delete()
c_count, _ = Contract.objects.filter(creator__account__is_test=True, title__startswith='E2E-').delete()
p_count, _ = Post.objects.filter(author__account__is_test=True, title__startswith='E2E-').delete()
print(f'Cleaned up {e_count} E2E events, {c_count} E2E contracts, {p_count} E2E blog posts')
"`,
      { timeout: 30_000, encoding: 'utf-8' },
    );
    const lastLine = dataResult.trim().split('\n').pop();
    console.log(`[e2e teardown] ${lastLine}`);
  } catch (err) {
    console.warn('[e2e teardown] Failed to cleanup E2E test data:', err);
  }

  // Step 2: Clean up e2etest user accounts
  try {
    const result = execSync(
      `python3 /opt/parahub/manage.py shell -c "
from identity.models import Profile, Account
profiles = Profile.objects.filter(local_name__startswith='e2etest')
account_ids = set(profiles.values_list('account_id', flat=True))
p_count = profiles.count()
profiles.delete()
a_count, _ = Account.objects.filter(id__in=account_ids).delete()
print(f'Cleaned up {p_count} e2etest profiles, {a_count} accounts')
"`,
      { timeout: 30_000, encoding: 'utf-8' },
    );
    const lastLine = result.trim().split('\n').pop();
    console.log(`[e2e teardown] ${lastLine}`);
  } catch (err) {
    console.warn('[e2e teardown] Failed to cleanup e2etest users:', err);
  }
}
