import type { GlobalThemeOverrides } from 'naive-ui'

export const lightThemeOverrides: GlobalThemeOverrides = {
  common: {
    primaryColor: '#665CA2',
    primaryColorHover: '#7B6FB8',
    primaryColorPressed: '#554A8E',
    bodyColor: '#FCFAFA',
    cardColor: '#FCFAFA',
    modalColor: '#FCFAFA',
    dividerColor: '#E0DCD7',
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
    borderColor: '#E0DCD7',
    color: '#FCFAFA',
    shadow: '0 1px 3px rgba(0, 0, 0, 0.06)',
  },
  Input: {
    borderRadius: '8px',
    border: '1px solid #E0DCD7',
    borderHover: '1px solid #C5C0BA',
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
    cardColor: '#1E1E20',
    modalColor: '#1E1E20',
    dividerColor: '#3A3A3E',
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
    borderColor: '#3A3A3E',
    color: '#1E1E20',
    shadow: '0 1px 3px rgba(0, 0, 0, 0.3)',
  },
  Input: {
    borderRadius: '8px',
    border: '1px solid #3A3A3E',
    borderHover: '1px solid #4A4A4E',
    borderFocus: '1px solid #8B7FD4',
  },
  Tag: {
    borderRadius: '6px',
  },
}
