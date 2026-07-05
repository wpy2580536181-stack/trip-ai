import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import HelloWorld from '../HelloWorld.vue'

describe('HelloWorld.vue', () => {
  it('renders title text', () => {
    const wrapper = mount(HelloWorld)
    expect(wrapper.text()).toContain('Get started')
  })

  it('renders documentation links', () => {
    const wrapper = mount(HelloWorld)
    const links = wrapper.findAll('a')
    expect(links.length).toBeGreaterThanOrEqual(4)
    expect(links[0].attributes('href')).toBe('https://vite.dev/')
  })

  it('increments count on button click', async () => {
    const wrapper = mount(HelloWorld)
    const button = wrapper.find('button.counter')
    expect(button.text()).toContain('Count is 0')
    await button.trigger('click')
    expect(button.text()).toContain('Count is 1')
  })

  it('renders Vite logo image', () => {
    const wrapper = mount(HelloWorld)
    const viteImg = wrapper.find('img.vite')
    expect(viteImg.exists()).toBe(true)
    expect(viteImg.attributes('alt')).toBe('Vite logo')
  })
})
