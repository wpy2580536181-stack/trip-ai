import type { GlobalThemeOverrides } from 'naive-ui'

export const lightThemeOverrides: GlobalThemeOverrides = {
  common: {
    primaryColor: '#665CA2',
    primaryColorHover: '#7B6FB8',
    primaryColorPressed: '#554A8E',
    bodyColor: '#FCFAFA',
    cardColor: '#F5F2ED',
    modalColor: '#F5F2ED',
    dividerColor: '#EAE5E0',
    textColor1: '#2B2D31',
    textColor2: '#6C6E74',
    textColor3: '#9B9BA0',
    borderRadius: '12px',
    fontSize: '14px',
    fontSizeSmall: '12px',
    fontSizeMedium: '14px',
    fontSizeLarge: '16px',
    heightMedium: '40px',
  },
  Button: {
    borderRadius: '10px',
    fontWeight: '600',
    colorPrimary: '#665CA2',
    colorHoverPrimary: '#7B6FB8',
    colorPressedPrimary: '#554A8E',
  },
  Card: {
    borderRadius: '12px',
    borderColor: '#EAE5E0',
  },
  Input: {
    borderRadius: '8px',
    border: '1px solid #EAE5E0',
    borderHover: '1px solid #665CA2',
    borderFocus: '1px solid #665CA2',
  },
  Tag: {
    borderRadius: '6px',
  },
}

export const darkThemeOverrides: GlobalThemeOverrides = {
  common: {
    primaryColor: '#8B7FD4',
    primaryColorHover: '#9E93E0',
    primaryColorPressed: '#776CCC',
    bodyColor: '#1E1E20',
    cardColor: '#262628',
    modalColor: '#262628',
    dividerColor: '#2E2E32',
    textColor1: '#E4E4E4',
    textColor2: '#9B9BA0',
    textColor3: '#6C6E74',
    borderRadius: '12px',
    fontSize: '14px',
    heightMedium: '40px',
  },
  Button: {
    borderRadius: '10px',
    fontWeight: '600',
    colorPrimary: '#8B7FD4',
    colorHoverPrimary: '#9E93E0',
    colorPressedPrimary: '#776CCC',
  },
  Card: {
    borderRadius: '12px',
    borderColor: '#2E2E32',
  },
  Input: {
    borderRadius: '8px',
    border: '1px solid #2E2E32',
    borderHover: '1px solid #8B7FD4',
    borderFocus: '1px solid #8B7FD4',
  },
  Tag: {
    borderRadius: '6px',
  },
}
