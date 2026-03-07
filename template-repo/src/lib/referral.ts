import type { SupabaseClient } from '@supabase/supabase-js';

const REFERRAL_CODE_CHARS = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789';
const REFERRAL_CODE_LENGTH = 8;

export function generateReferralCode(): string {
  let result = '';
  for (let i = 0; i < REFERRAL_CODE_LENGTH; i++) {
    result += REFERRAL_CODE_CHARS.charAt(
      Math.floor(Math.random() * REFERRAL_CODE_CHARS.length)
    );
  }
  return result;
}

export async function validateReferralCode(
  supabase: SupabaseClient,
  code: string
): Promise<{ valid: boolean; referrerId?: string }> {
  if (!code || code.length !== REFERRAL_CODE_LENGTH) {
    return { valid: false };
  }

  const { data, error } = await supabase
    .from('profiles')
    .select('id')
    .eq('referral_code', code.toUpperCase())
    .single();

  if (error || !data) {
    return { valid: false };
  }

  return { valid: true, referrerId: data.id };
}

export async function applyReferralReward(
  supabase: SupabaseClient,
  referrerId: string,
  refereeId: string
): Promise<{ success: boolean; error?: string }> {
  const { data: referral } = await supabase
    .from('referrals')
    .select('id, reward_applied')
    .eq('referrer_id', referrerId)
    .eq('referee_id', refereeId)
    .single();

  if (!referral) {
    return { success: false, error: 'Referral record not found' };
  }

  if (referral.reward_applied) {
    return { success: true }; // Already applied
  }

  const { error } = await supabase
    .from('referrals')
    .update({ status: 'rewarded', reward_applied: true })
    .eq('id', referral.id);

  if (error) {
    return { success: false, error: error.message };
  }

  return { success: true };
}
