import { render, screen } from '@testing-library/react';
import App from './App';

describe('App', () => {
  it('renders the Market Briefing Agent heading', () => {
    render(<App />);
    expect(
      screen.getByRole('heading', { name: /market briefing agent/i }),
    ).toBeInTheDocument();
  });
});
