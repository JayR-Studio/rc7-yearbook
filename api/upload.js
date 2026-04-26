import { put } from '@vercel/blob';

export default async function handler(req, res) {
  if (req.method !== 'POST') {
    return res.status(405).json({ message: 'Method not allowed' });
  }

  const filename = req.headers['x-vercel-filename'] || 'upload';
  const blob = await put(filename, req, {
    access: 'public',
  });

  return res.status(200).json(blob);
}