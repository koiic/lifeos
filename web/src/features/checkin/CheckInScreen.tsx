import { useRef, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';

import { formatIsoDate, nowIso } from '../../lib/dates';
import { useMe } from '../../lib/me/me';
import { CheckInSheet } from './CheckInSheet';

/**
 * Route screen for `/checkin` (spec 5.2, CHK-1).
 * Opens the check-in bottom sheet for the specified date (defaulting to today).
 */
export function CheckInScreen() {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const me = useMe();
  const [open, setOpen] = useState(true);
  const closingRef = useRef(false);

  const timezone = me.data?.profile.timezone;
  const date = searchParams.get('date') ?? formatIsoDate(nowIso(), timezone);
  const moodParam = searchParams.get('mood');
  const initialMood = moodParam ? Number(moodParam) : undefined;

  const handleClose = () => {
    if (closingRef.current) return;
    closingRef.current = true;
    setOpen(false);
    if (window.history.state && window.history.state.idx > 0) {
      navigate(-1);
    } else {
      navigate('/today', { replace: true });
    }
  };

  return (
    <CheckInSheet
      open={open}
      date={date}
      initialMood={initialMood}
      onClose={handleClose}
      onSaved={handleClose}
    />
  );
}
