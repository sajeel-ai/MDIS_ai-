import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import React from 'react';
import { Sidebar } from '../components/navigation/Sidebar';

describe('Item 2: Workflows feature flag & navigation hiding', () => {
  beforeEach(() => {
    delete (window as any).__ENABLE_WORKFLOWS__;
  });

  afterEach(() => {
    delete (window as any).__ENABLE_WORKFLOWS__;
  });

  it('hides Workflows from navigation by default', () => {
    render(<Sidebar activeView="dashboard" onNavigate={vi.fn()} />);
    expect(screen.queryByRole('button', { name: /Workflows/i })).toBeNull();
  });

  it('shows Workflows in navigation when window.__ENABLE_WORKFLOWS__ is true', () => {
    (window as any).__ENABLE_WORKFLOWS__ = true;
    render(<Sidebar activeView="dashboard" onNavigate={vi.fn()} />);
    expect(screen.getByRole('button', { name: /Workflows/i })).toBeInTheDocument();
  });
});

