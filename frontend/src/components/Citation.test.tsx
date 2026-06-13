import { render, screen } from '@testing-library/react';
import { CitationChip, InlineCites } from './Citation';
import type { Citation } from '../lib/types';

const mockCitations: Citation[] = [
  {
    id: 'c1',
    kind: 'tool',
    title: 'Market-data tools',
    url: null,
  },
  {
    id: 'c2',
    kind: 'news',
    title: 'AAPL Stock Slides Following WWDC',
    url: 'https://www.macrumors.com/2026/06/11/aapl-stock-slides/',
  },
];

describe('CitationChip', () => {
  it('renders the citation id', () => {
    render(<CitationChip id="c1" citations={mockCitations} />);
    expect(screen.getByText('[c1]')).toBeInTheDocument();
  });

  it('renders popover with title', () => {
    render(<CitationChip id="c2" citations={mockCitations} />);
    expect(screen.getByText('AAPL Stock Slides Following WWDC')).toBeInTheDocument();
  });

  it('renders popover with domain for news citation', () => {
    render(<CitationChip id="c2" citations={mockCitations} />);
    expect(screen.getByText('www.macrumors.com')).toBeInTheDocument();
  });

  it('renders kind label', () => {
    render(<CitationChip id="c2" citations={mockCitations} />);
    expect(screen.getByText('news · c2')).toBeInTheDocument();
  });

  it('renders gracefully for unknown id', () => {
    render(<CitationChip id="c99" citations={mockCitations} />);
    expect(screen.getByText('[c99]')).toBeInTheDocument();
  });
});

describe('InlineCites', () => {
  it('renders nothing when ids is empty', () => {
    const { container } = render(<InlineCites ids={[]} citations={mockCitations} />);
    expect(container.firstChild).toBeNull();
  });

  it('renders multiple citation chips', () => {
    render(<InlineCites ids={['c1', 'c2']} citations={mockCitations} />);
    expect(screen.getByText('[c1]')).toBeInTheDocument();
    expect(screen.getByText('[c2]')).toBeInTheDocument();
  });
});
