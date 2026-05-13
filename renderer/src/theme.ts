import { loadFont as loadFraunces } from '@remotion/google-fonts/Fraunces';
import { loadFont as loadInter } from '@remotion/google-fonts/Inter';

const fraunces = loadFraunces('normal', {
  weights: ['300', '400', '500', '600', '700'],
  subsets: ['latin'],
});
const inter = loadInter('normal', {
  weights: ['400', '500', '700'],
  subsets: ['latin'],
});

export const theme = {
  brandGreen: '#0E5C4A',
  brandGreenDark: '#0A4438',
  brandGreenDeep: '#08382C',
  brandGreenLight: '#14705C',
  gold: '#E9C46A',
  white: '#FFFFFF',
  cream: '#FBF7F1',
  fraunces: fraunces.fontFamily,
  inter: inter.fontFamily,
  // Warm cinematic grade applied at the composition root.
  warmGrade: 'saturate(0.92) contrast(1.06) brightness(1.02) sepia(0.10) hue-rotate(-4deg)',
  // Caption surface — frosted brand-tint glass.
  captionBg: 'rgba(14, 92, 74, 0.22)',
  captionShadow: '0 1px 2px rgba(0,0,0,0.45), 0 6px 24px rgba(0,0,0,0.40)',
};
