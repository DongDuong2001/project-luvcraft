import { describe, expect, it } from 'vitest';
import { balanceWeights } from '../components/sections/BrandCollaboration';

describe('balanceWeights', () => {
  it('uses largest remainders to produce an exact 100 percent total', () => {
    const balanced = balanceWeights({ audience: 1, affinity: 1, reach: 1, safety: 1, relevance: 1, momentum: 1 });

    expect(Object.values(balanced).reduce((sum, value) => sum + value, 0)).toBe(100);
    expect(balanced).toEqual({ audience: 17, affinity: 17, reach: 17, safety: 17, relevance: 16, momentum: 16 });
  });

  it('clamps negative inputs before balancing', () => {
    const balanced = balanceWeights({ audience: -20, affinity: 3, reach: 1 });

    expect(balanced).toEqual({ audience: 0, affinity: 75, reach: 25 });
    expect(Object.values(balanced).reduce((sum, value) => sum + value, 0)).toBe(100);
  });

  it('distributes evenly when all inputs are zero', () => {
    expect(balanceWeights({ audience: 0, affinity: 0, reach: 0 })).toEqual({ audience: 34, affinity: 33, reach: 33 });
  });
});
