import { render, screen } from '@testing-library/react';
import App from './App';

describe('App', () => {
  it('renders the Market Briefing Agent heading', () => {
    render(<App />);
    // Home view shows the h1 with product name
    expect(
      screen.getByRole('heading', { name: /market briefing agent/i }),
    ).toBeInTheDocument();
  });

  it('renders the value prop text on home', () => {
    render(<App />);
    expect(screen.getByText(/watch an agent/i)).toBeInTheDocument();
  });

  it('renders example ticker chips', () => {
    render(<App />);
    expect(screen.getByRole('button', { name: /aapl/i })).toBeInTheDocument();
  });
});
