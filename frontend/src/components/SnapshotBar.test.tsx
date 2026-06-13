import { render, screen } from '@testing-library/react';
import { SnapshotBar } from './SnapshotBar';
import type { Snapshot } from '../lib/types';

const mockSnapshot: Snapshot = {
  price: 291.13,
  change_1d: -1.52,
  change_1m: -2.59,
  change_period: 16.5,
  market_cap: '$4.28T',
  pe: 35.2,
  sector: 'Technology',
  low_52w: 194.87,
  high_52w: 315.2,
};

describe('SnapshotBar', () => {
  it('renders all 6 cells', () => {
    render(<SnapshotBar snapshot={mockSnapshot} period="3mo" />);
    expect(screen.getByText('Price')).toBeInTheDocument();
    expect(screen.getByText('1D')).toBeInTheDocument();
    expect(screen.getByText('1M')).toBeInTheDocument();
    expect(screen.getByText('3mo')).toBeInTheDocument();
    expect(screen.getByText('Mkt Cap')).toBeInTheDocument();
    expect(screen.getByText('P/E')).toBeInTheDocument();
  });

  it('renders the price correctly', () => {
    render(<SnapshotBar snapshot={mockSnapshot} period="3mo" />);
    expect(screen.getByText('$291.13')).toBeInTheDocument();
  });

  it('renders negative 1D change with neg class', () => {
    render(<SnapshotBar snapshot={mockSnapshot} period="3mo" />);
    const cell = screen.getByText('−1.52%');
    expect(cell).toHaveClass('neg');
  });

  it('renders positive period change with pos class', () => {
    render(<SnapshotBar snapshot={mockSnapshot} period="3mo" />);
    const cell = screen.getByText('+16.50%');
    expect(cell).toHaveClass('pos');
  });

  it('renders market cap', () => {
    render(<SnapshotBar snapshot={mockSnapshot} period="3mo" />);
    expect(screen.getByText('$4.28T')).toBeInTheDocument();
  });

  it('renders P/E', () => {
    render(<SnapshotBar snapshot={mockSnapshot} period="3mo" />);
    expect(screen.getByText('35.2')).toBeInTheDocument();
  });

  it('renders N/A for null P/E', () => {
    const snap = { ...mockSnapshot, pe: null };
    render(<SnapshotBar snapshot={snap} period="3mo" />);
    expect(screen.getByText('N/A')).toBeInTheDocument();
  });
});
